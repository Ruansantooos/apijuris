"""Adapter de consulta ao TJSP (e-SAJ, com fallback para o EPROC).

Usa undetected-chromedriver dentro de um display virtual (Xvfb) em vez do modo
--headless nativo do Chrome: sites protegidos por Cloudflare/anti-bot (como o
e-SAJ) costumam detectar e bloquear o headless nativo, mas não distinguem um
Chrome "de cabeça" rodando contra um display virtual sem monitor real.
"""
import logging
import re
import threading
from contextlib import contextmanager

import psutil
import undetected_chromedriver as uc
from bs4 import BeautifulSoup, NavigableString
from selenium.common.exceptions import (
    NoAlertPresentException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.adapters.base import (
    CaptchaRequiredError,
    ConsultaResultado,
    InvalidProcessError,
    Movimentacao,
    NotFoundError,
    ParserError,
    SourceTimeoutError,
    SourceUnavailableError,
    TribunalAdapter,
)
from app.cnj import clean_cnj, formatar_cnj
from app.config import settings

log = logging.getLogger("adapters.tjsp")

# Só um Chrome roda por vez: a VPS tem memória limitada e cada instância consome
# várias centenas de MB. Consultas concorrentes entram na fila em vez de disputar RAM.
_scrape_lock = threading.Semaphore(settings.scraper_max_concurrency)


def _processos_do_driver(driver: uc.Chrome) -> list[psutil.Process]:
    """Chrome + chromedriver e todos os filhos (renderers, GPU, etc.).

    Precisa ser coletado ANTES do quit(): depois que o pai morre, os filhos órfãos
    são adotados pelo init e não aparecem mais em children().
    """
    raizes = []
    for pid in (getattr(driver, "browser_pid", None), getattr(driver.service.process, "pid", None)):
        if pid:
            try:
                raizes.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                pass

    processos = list(raizes)
    for raiz in raizes:
        try:
            processos.extend(raiz.children(recursive=True))
        except psutil.NoSuchProcess:
            pass
    return processos


def _matar_sobreviventes(processos: list[psutil.Process]) -> None:
    # psutil confere o create_time antes do kill: se o PID foi reaproveitado por
    # outro processo do sistema, ele levanta NoSuchProcess em vez de matar o errado.
    for proc in processos:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


@contextmanager
def _driver_session():
    display = None
    if settings.scraper_use_xvfb:
        from pyvirtualdisplay import Display

        display = Display(visible=0, size=(1920, 1080))
        display.start()

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--incognito")
    if settings.chrome_binary:
        options.binary_location = settings.chrome_binary

    driver = None
    try:
        driver = uc.Chrome(options=options)
        yield driver
    finally:
        # Um Chrome que não morre a cada consulta vaza centenas de MB; poucas
        # consultas com falha bastariam para esgotar a memória da VPS.
        if driver is not None:
            processos = _processos_do_driver(driver)
            try:
                driver.quit()
            except Exception:
                log.warning("driver.quit() falhou; encerrando processos do Chrome à força")
            _matar_sobreviventes(processos)
        if display is not None:
            display.stop()


_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")

_POLO_ATIVO = ("reqte", "requerente", "autor", "exeqte", "exequente", "impetrante",
               "embargte", "apelante", "credor", "agravante")
_POLO_PASSIVO = ("reqdo", "reqda", "requerido", "requerida", "réu", "reu", "executado",
                 "impetrado", "embargdo", "apelado", "devedor", "agravado")


def _polo_da_parte(tipo: str) -> str:
    t = tipo.strip().lower().rstrip(".:")
    if t.startswith(_POLO_ATIVO):
        return "ATIVO"
    if t.startswith(_POLO_PASSIVO):
        return "PASSIVO"
    return tipo.strip().upper()


def _expandir_movimentacoes(driver: uc.Chrome) -> None:
    """O e-SAJ não traz as movimentações no HTML inicial: a página vem com um
    #containerMovimentacoes vazio e o botão "Exibir movimentações", que carrega o
    conteúdo por AJAX. Sem este clique a extração volta sempre vazia."""
    containers = driver.find_elements(By.ID, "containerMovimentacoes")
    botoes = driver.find_elements(By.ID, "btnExibirMovimentacoes")
    if not containers or not botoes:
        return  # layout antigo (movimentações já na página) ou já expandido

    tamanho_inicial = len(containers[0].get_attribute("innerHTML") or "")
    driver.execute_script("arguments[0].click();", botoes[0])
    try:
        WebDriverWait(driver, settings.scraper_timeout_seconds).until(
            lambda d: len(
                d.find_element(By.ID, "containerMovimentacoes").get_attribute("innerHTML") or ""
            ) > tamanho_inicial + 200
        )
    except TimeoutException:
        log.warning("Movimentações do e-SAJ não carregaram após o clique")


def _extrair_partes(soup: BeautifulSoup) -> list[dict]:
    """Cada linha: <span class="tipoDeParticipacao">Reqte</span> e um
    td.nomeParteEAdvogado com o nome da parte, um <br>, e depois os advogados."""
    tabela = soup.find(id="tablePartesPrincipais") or soup.find(id="tableTodasPartes")
    if not tabela:
        return []

    partes = []
    for linha in tabela.find_all("tr"):
        tipo_el = linha.find("span", class_="tipoDeParticipacao")
        celula = linha.find("td", class_="nomeParteEAdvogado")
        if not tipo_el or not celula:
            continue

        nome = ""
        for filho in celula.contents:
            if getattr(filho, "name", None) == "br":
                break
            if isinstance(filho, NavigableString):
                nome = " ".join(str(filho).split())
                if nome:
                    break

        advogados = []
        for span in celula.find_all("span", class_="mensagemExibindo"):
            seguinte = span.next_sibling
            adv = " ".join(str(seguinte).split()) if seguinte else ""
            if adv:
                advogados.append(adv)

        tipo = " ".join(tipo_el.get_text().split())
        if nome:
            partes.append(
                {"nome": nome, "polo": _polo_da_parte(tipo), "tipo": tipo, "advogados": advogados}
            )
    return partes


def _extrair_movimentacoes_esaj(soup: BeautifulSoup) -> list[Movimentacao]:
    # A tabela é buscada DENTRO do container: a mesma página tem a tabela
    # "Petições diversas", também com datas, que não é andamento do processo.
    tabela = None
    container = soup.find(id="containerMovimentacoes")
    if container:
        tabela = container.find("table")
    if tabela is None:
        tabela = soup.find(id="tabelaTodasMovimentacoes") or soup.find(id="tabelaUltimasMovimentacoes")
    if tabela is None:
        return []

    movimentacoes = []
    for linha in tabela.find_all("tr"):
        celulas = linha.find_all("td")
        if len(celulas) < 2:
            continue
        data_raw = " ".join(celulas[0].get_text().split())
        if not _RE_DATA.match(data_raw):
            continue  # cabeçalho e linhas de espaçamento
        descricao = " ".join(celulas[-1].get_text().split())
        if descricao:
            movimentacoes.append(Movimentacao(descricao=descricao, data_raw=data_raw))
    return movimentacoes


def _scrape_eproc(driver: uc.Chrome, numero_cnj: str) -> ConsultaResultado:
    wait = WebDriverWait(driver, settings.scraper_timeout_seconds)
    log.info("Tentando EPROC para %s", numero_cnj)
    driver.get(
        "https://eproc-consulta.tjsp.jus.br/consulta_1g/externo_controlador.php"
        "?acao=tjsp@consulta_unificada_publica/consultar"
    )

    campo = None
    for seletor in ("txtNumProcesso", "txtNumeroProcesso", "txtProcesso"):
        try:
            campo = wait.until(EC.presence_of_element_located((By.ID, seletor)))
            break
        except TimeoutException:
            continue
    if campo is None:
        raise SourceUnavailableError("Campo de busca do EPROC não encontrado")

    campo.clear()
    campo.send_keys(numero_cnj)

    botao = None
    for seletor in ("btnConsultar", "btnPesquisar"):
        try:
            botao = driver.find_element(By.ID, seletor)
            break
        except WebDriverException:
            continue
    if botao is None:
        botao = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    botao.click()

    # O EPROC protege a consulta com captcha: se o clique dispara o alerta
    # "Aguarde a verificação do captcha", a busca não aconteceu.
    try:
        alerta = driver.switch_to.alert
        texto_alerta = alerta.text
        alerta.accept()
        raise CaptchaRequiredError(f"EPROC exige captcha: {texto_alerta}")
    except NoAlertPresentException:
        pass

    try:
        wait.until(
            lambda d: "tabelaEventos" in d.page_source
            or "Nenhum registro encontrado" in d.page_source
        )
    except TimeoutException:
        raise SourceTimeoutError("EPROC não respondeu dentro do tempo limite")

    if "Nenhum registro encontrado" in driver.page_source:
        raise NotFoundError("Processo não encontrado no EPROC")

    # Sem a tabela de eventos a leitura falhou (captcha, layout novo). Devolver
    # zero movimentações seria pior: o cliente veria "processo sem andamento".
    if not driver.find_elements(By.ID, "tabelaEventos"):
        raise ParserError("EPROC não devolveu a tabela de eventos")

    soup = BeautifulSoup(driver.page_source, "html.parser")

    classe, assunto = "N/A", "N/A"
    for rotulo in soup.find_all(["label", "th"]):
        texto = rotulo.get_text().strip()
        if "Classe" in texto:
            valor = rotulo.find_next(["span", "td", "div"])
            if valor:
                classe = valor.get_text().strip()
        elif "Assunto" in texto:
            valor = rotulo.find_next(["span", "td", "div"])
            if valor:
                assunto = valor.get_text().strip()

    movimentacoes = []
    tabela = soup.find("table", {"id": "tabelaEventos"})
    if tabela:
        for linha in tabela.find_all("tr")[1:]:
            celulas = linha.find_all("td")
            if len(celulas) >= 3:
                data_raw = celulas[1].get_text().strip()
                descricao = " ".join(celulas[2].get_text().split())
                movimentacoes.append(Movimentacao(descricao=descricao, data_raw=data_raw))

    return ConsultaResultado(
        numero=numero_cnj,
        tribunal="TJSP",
        fonte="EPROC-TJSP",
        classe=classe,
        assunto=assunto,
        partes=[],
        movimentacoes=movimentacoes,
    )


def _scrape_esaj(driver: uc.Chrome, numero_cnj: str) -> ConsultaResultado:
    clean = clean_cnj(numero_cnj)
    primeira_parte = f"{clean[0:7]}-{clean[7:9]}.{clean[9:13]}"
    foro = clean[16:20]
    numero_formatado = formatar_cnj(clean)

    wait = WebDriverWait(driver, settings.scraper_timeout_seconds)
    log.info("Consultando e-SAJ para %s", numero_formatado)
    driver.get("https://esaj.tjsp.jus.br/cpopg/open.do")

    try:
        campo_numero = wait.until(EC.presence_of_element_located((By.ID, "numeroDigitoAnoUnificado")))
        campo_numero.clear()
        campo_numero.send_keys(primeira_parte)
        driver.find_element(By.ID, "foroNumeroUnificado").clear()
        driver.find_element(By.ID, "foroNumeroUnificado").send_keys(foro)
        driver.find_element(By.ID, "botaoConsultarProcessos").click()
        wait.until(
            lambda d: "classeProcesso" in d.page_source
            or "Não existem informações disponíveis" in d.page_source
        )
    except TimeoutException:
        log.warning("Busca padrão do e-SAJ expirou, tentando via CNJ completo")

    if (
        "Não existem informações disponíveis" in driver.page_source
        or "numeroDigitoAnoUnificado" in driver.page_source
    ):
        driver.get("https://esaj.tjsp.jus.br/cpopg/open.do")
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "radioOutros"))).click()
            campo_outros = wait.until(
                EC.presence_of_element_located((By.ID, "dadosConsulta.valorConsulta"))
            )
            campo_outros.clear()
            campo_outros.send_keys(numero_formatado)
            driver.find_element(By.ID, "botaoConsultarProcessos").click()
            wait.until(
                lambda d: "classeProcesso" in d.page_source
                or "Não existem informações disponíveis" in d.page_source
            )
        except TimeoutException:
            pass

    if (
        "Não existem informações disponíveis" in driver.page_source
        or "numeroDigitoAnoUnificado" in driver.page_source
    ):
        return _scrape_eproc(driver, numero_formatado)

    _expandir_movimentacoes(driver)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    classe_el = soup.find(id="classeProcesso")
    assunto_el = soup.find(id="assuntoProcesso")

    movimentacoes = _extrair_movimentacoes_esaj(soup)
    if not movimentacoes:
        raise ParserError("Página do e-SAJ carregou mas nenhuma movimentação pôde ser extraída")

    return ConsultaResultado(
        numero=numero_formatado,
        tribunal="TJSP",
        fonte="e-SAJ-TJSP",
        classe=classe_el.get_text().strip() if classe_el else "N/A",
        assunto=assunto_el.get_text().strip() if assunto_el else "N/A",
        partes=_extrair_partes(soup),
        movimentacoes=movimentacoes,
    )


class TJSPAdapter(TribunalAdapter):
    def consultar_processo(self, numero: str) -> ConsultaResultado:
        clean = clean_cnj(numero)
        if len(clean) != 20:
            raise InvalidProcessError("CNJ inválido - deve ter 20 dígitos")

        acquired = _scrape_lock.acquire(timeout=settings.scraper_timeout_seconds * 4)
        if not acquired:
            raise SourceUnavailableError("Fila de consultas ao TJSP está cheia, tente novamente")

        # Mensagens do Selenium trazem stacktrace, caminhos e versões internas: vão só
        # para o log. O cliente da API recebe uma mensagem genérica.
        try:
            with _driver_session() as driver:
                try:
                    return _scrape_esaj(driver, clean)
                except TimeoutException as exc:
                    log.warning("Timeout consultando %s: %s", clean, exc)
                    raise SourceTimeoutError("A fonte não respondeu dentro do tempo limite") from exc
                except WebDriverException as exc:
                    log.exception("Falha do navegador consultando %s", clean)
                    raise SourceUnavailableError("Falha ao acessar a fonte do tribunal") from exc
        finally:
            _scrape_lock.release()
