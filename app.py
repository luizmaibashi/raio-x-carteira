"""Raio-X da Carteira — tela (Streamlit). Rode: streamlit run app.py"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
from decimal import Decimal
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from raio_x.das import ForaDoEscopo, calcular
from raio_x.entrada import TOMADORES_CREDITO, ErroEntrada, ler_carteira_csv, ler_linhas_csv
from raio_x.modelo import avaliar_carteira, linha_do_tempo, poder_de_preco_indiferenca
from raio_x.nfse import ErroNFSe, ler_notas
from raio_x.painel import ANOS, DIFERENCA, brl, caso_conferido, ler_conferencia, pct, sensibilidade_r, t_por_ano, tabela_clientes

RAIZ = Path(__file__).resolve().parent
EXEMPLOS = RAIZ / "dados" / "exemplos"
PERFIS = {p["nome"]: p for p in json.loads((EXEMPLOS / "perfis.json").read_text(encoding="utf-8"))}
EXEMPLO_XML = RAIZ / "dados" / "exemplos" / "nfse"
CONFERENCIA = RAIZ / "dados" / "conferencia_receita.json"
EXPLICACOES = RAIZ / "dados" / "explicacoes_ia.json"
# P03: quem optou por IBS/CBS por fora no 1º semestre de 2027 pode cancelar até 20/12/2026.
PRAZO_CANCELAMENTO = dt.date(2026, 12, 20)
OPCOES_TOMADOR = list(TOMADORES_CREDITO)
ROTULOS_TOMADOR = {"regular": "regular (empresa no regime regular)", "simples_h": "simples_h (Simples com IBS/CBS por fora)",
                   "simples": "simples (Simples puro)", "pf": "pf (pessoa física)", "isento": "isento"}

st.set_page_config(page_title="Raio-X da Carteira", page_icon=":material/receipt_long:", layout="wide")
st.markdown(f"<style>{(RAIZ / 'raio_x' / 'estilo.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

SOBRE = ("Reforma tributária para prestador de serviço do Simples Nacional que vende para empresas: "
         "cliente a cliente, vale ficar no Simples puro ou recolher IBS/CBS por fora?")
AVISO = "Protótipo do Hack Brasil 2026, só com dados sintéticos. Não é consultoria tributária."

# Ordem na página: veredito, os dois controles que mais mexem nele, resultado e só depois a carteira editável.
topo, area_controles, area_resultado, area_carteira = (st.container() for _ in range(4))


def _topo(olho: str, veredito: str, apoio: str, nota: str = AVISO) -> None:
    """Cabeçalho. Anima só na primeira carga da sessão (entrada única, sem repetir a cada ajuste)."""
    entra = "" if st.session_state.get("_entrou") else " rx-entra"
    st.session_state._entrou = True
    topo.markdown(f'<div class="rx-topo{entra}"><p class="rx-olho">{olho}</p><p class="rx-veredito" role="heading" aria-level="1">{veredito}</p>'
                  f'<p class="rx-apoio">{apoio}</p><p class="rx-nota">{nota}</p></div>', unsafe_allow_html=True)


def _secao(onde, titulo: str, sub: str = "") -> None:
    onde.markdown(f'<div class="rx-secao"><h3>{titulo}</h3>' + (f'<p class="rx-sub">{sub}</p>' if sub else "") + "</div>",
                  unsafe_allow_html=True)


# ---------------------------------------------------------------- entrada
def _df_de_csv(texto: str) -> pd.DataFrame:
    return pd.DataFrame([{"cliente": n, "valor_12m": float(v), "tomador": t}
                         for n, v, t in ler_linhas_csv(io.StringIO(texto))])


def _df_de_xml(arquivos) -> tuple[pd.DataFrame, str]:
    r = ler_notas(arquivos)
    df = pd.DataFrame([{"cliente": t.rotulo, "valor_12m": float(t.valor),
                        "tomador": "pf" if t.tipo == "pf" else None} for t in r.tomadores])
    resumo = (f"{r.notas_lidas} notas lidas, {len(r.tomadores)} tomadores, {r.duplicadas} duplicadas ignoradas. "
              "CPFs descartados na leitura; pessoas físicas agregadas numa linha.")
    return df.sort_values("valor_12m", ascending=False, ignore_index=True), resumo


def _carregar(df: pd.DataFrame, resumo: str, perfil: str | None = None) -> None:
    """Troca a carteira; a versão nova recria a tabela editável (edições da carteira anterior não vazam)."""
    st.session_state.carteira, st.session_state.resumo, st.session_state.perfil_ativo = df, resumo, perfil
    st.session_state.versao = st.session_state.get("versao", 0) + 1


def _carregar_perfil() -> None:
    p = PERFIS[st.session_state.perfil]
    df = _df_de_csv((EXEMPLOS / p["arquivo"]).read_text(encoding="utf-8"))
    _carregar(df, f"{p['resumo']} Carteira sintética de {len(df)} clientes; edite à vontade.", p["nome"])
    st.session_state.folha, st.session_state.reducao = float(p["folha12"]), p["reducao_30"]


if "carteira" not in st.session_state:   # abre já com um perfil sintético: a tela nunca começa vazia
    st.session_state.perfil = next(iter(PERFIS))
    _carregar_perfil()

with st.sidebar:
    st.header("1. Sua carteira")
    fonte = st.radio("Como entrar com os clientes", ["Exemplo sintético", "CSV", "XMLs de NFS-e"], index=0)
    try:
        if fonte == "Exemplo sintético":
            st.selectbox("Perfil", list(PERFIS), key="perfil", on_change=_carregar_perfil,
                         help="Três prestadores sintéticos com respostas diferentes.")
            c1, c2 = st.columns(2)
            if c1.button("Recarregar", width="stretch"):
                _carregar_perfil()
            if c2.button("Notas (XML)", width="stretch"):
                arqs = [(p.name, p.read_bytes()) for p in sorted(EXEMPLO_XML.glob("*.xml"))]
                _carregar(*_df_de_xml(arqs))
        elif fonte == "CSV":
            st.caption("Colunas: `cliente;valor_12m;tomador`")
            up = st.file_uploader("Arquivo CSV", type=["csv"])
            if up is not None and st.session_state.get("_csv") != up.file_id:
                _carregar(_df_de_csv(up.getvalue().decode("utf-8-sig")), f"{up.name} carregado.")
                st.session_state._csv = up.file_id
        else:
            ups = st.file_uploader("XMLs das notas emitidas (padrão nacional)", type=["xml"],
                                   accept_multiple_files=True)
            chave = tuple(u.file_id for u in ups)
            if ups and st.session_state.get("_xml") != chave:
                _carregar(*_df_de_xml([(u.name, u.getvalue()) for u in ups]))
                st.session_state._xml = chave
    except (ErroEntrada, ErroNFSe) as e:
        st.error(str(e))

    st.header("2. Sua empresa")
    folha = st.number_input("Folha + pró-labore + encargos, 12 meses (R$)", min_value=0.0, step=1_000.0,
                            format="%.2f", key="folha")
    reducao = st.checkbox("Profissão regulamentada com redução de 30% (ex.: economista, contador)", key="reducao")
    k = st.number_input("Créditos de IBS/CBS das suas compras em H, 12 meses (R$)", min_value=0.0, value=0.0,
                        step=100.0, format="%.2f")

    st.header("3. Cenário")
    t33 = st.slider("CBS + IBS em 2033 (cenário, %)", 20.0, 32.0, 27.0, 0.5, format="%.1f%%",
                    help="Não há alíquota oficial de IBS ainda. O modelo usa estimativas de 26% a 28%. "
                         "Só 2027 (11,3%, TCU) é referência oficial.") / 100

# Os dois controles que mais mudam a resposta ficam junto do veredito (no celular a barra lateral começa fechada).
c_r, c_ano = area_controles.columns([3, 1], gap="large")
r = c_r.slider("Quanto do seu preço você consegue manter se recolher por fora?", 0, 100, 0, 5, format="%d%%",
               help="0%: você baixa o preço até o cliente pagar o mesmo de antes (ele dita o preço). "
                    "100%: você mantém o preço de hoje e o imposto vai por cima; o cliente absorve a diferença. "
                    "No modelo, é o poder de preço r.") / 100
ano = c_ano.selectbox("Ano", ANOS, index=0)

_secao(area_carteira, "Sua carteira", st.session_state.resumo or "Escolha uma entrada na barra lateral.")
editada = area_carteira.data_editor(
    st.session_state.carteira, num_rows="dynamic", width="stretch", hide_index=True,
    column_config={
        "cliente": st.column_config.TextColumn("Cliente", required=True),
        "valor_12m": st.column_config.NumberColumn("Faturado em 12 meses (R$)", min_value=0.0, format="localized",
                                                   required=True),
        "tomador": st.column_config.SelectboxColumn("Regime do cliente", options=OPCOES_TOMADOR, required=True,
                                                    help="; ".join(ROTULOS_TOMADOR.values())),
    }, key=f"editor_{st.session_state.versao}")

if editada.empty:
    _topo("Raio-X da Carteira", "Quanto a reforma muda, cliente a cliente.", SOBRE)
    area_resultado.info("A carteira está vazia. Carregue o exemplo na barra lateral ou inclua clientes na tabela.")
    st.stop()

faltando = editada[editada["tomador"].isna() | (editada["tomador"].astype(str).str.strip() == "")]
if not faltando.empty:
    _topo("Raio-X da Carteira", "Falta um dado para o raio-X.", SOBRE)
    area_resultado.warning("Informe o regime de: " + ", ".join(faltando["cliente"].astype(str)) +
                           ", na coluna **Regime do cliente** da tabela **Sua carteira**, logo abaixo. A nota fiscal não diz se o cliente "
                           "toma crédito; o protótipo não chuta.")
    st.stop()

try:
    texto = "cliente;valor_12m;tomador\n" + "\n".join(
        f"{str(l.cliente).replace(';', ',')};{Decimal(str(l.valor_12m)):.2f};{l.tomador}" for l in editada.itertuples())
    clientes = ler_carteira_csv(io.StringIO(texto))
    cred = {c.nome: c.cred for c in clientes}
    ts = t_por_ano(t33, reducao)
    t = ts[ano]
    das = calcular(sum(c.valor for c in clientes), folha, ano)
    res = avaliar_carteira(clientes, folha, ano, t, r, k)
except (ErroEntrada, ForaDoEscopo) as e:
    _topo("Raio-X da Carteira", "Essa carteira está fora do escopo.", SOBRE)
    area_resultado.error(f"Fora do escopo do protótipo: {e}")
    st.stop()

# ---------------------------------------------------------------- gráficos
# Polaridade (H ganha × H perde): par divergente azul/vermelho, validado contra os dois fundos,
# claro #f7f5f0 e escuro #1a1917 (skill dataviz: CVD ΔE 21,6, contraste ≥ 3:1). Texto dos eixos fica com
# o tema do Streamlit; grade e zero num cinza médio que serve aos dois temas. Cantos de 4px na ponta da barra.
GANHA, PERDE, NEUTRO = "#2a78d6", "#e34948", "#8a877f"
EIXO_BRL = "'R$ ' + replace(format(datum.value, ',.0f'), ',', '.')"
COR_SINAL = alt.condition("datum.v >= 0", alt.value(GANHA), alt.value(PERDE))


def _estilo(ch: alt.Chart) -> alt.Chart:
    return (ch.properties(padding={"left": 12, "right": 8, "top": 4, "bottom": 4})
            .configure(background="transparent", font="IBM Plex Sans")
            .configure_view(stroke=None)
            .configure_axis(titleFontWeight=500, labelFontSize=12, titleFontSize=12, gridColor=NEUTRO,
                            gridOpacity=0.25, domain=False, tickColor=NEUTRO, tickOpacity=0.4))


def _largura_rotulos(rotulos) -> int:
    """Reserva espaço para os nomes: o Vega mede antes de a fonte da web carregar e cortaria o rótulo."""
    return min(320, 12 + 7 * max((len(str(x)) for x in rotulos), default=0))


def _zero() -> alt.Chart:
    return alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color=NEUTRO, strokeWidth=1)


def _barras(df: pd.DataFrame, cat: str, val: str, horizontal: bool = False) -> alt.Chart:
    d = df[[cat, val]].rename(columns={cat: "c", val: "v"})
    d["rotulo"] = [brl(v) for v in d["v"]]
    eixo_v = alt.Axis(title="Diferença para você (R$)", labelExpr=EIXO_BRL)
    dica = [alt.Tooltip("c:N", title=cat), alt.Tooltip("v:Q", title=val, format=",.2f")]
    if horizontal:
        enc = dict(y=alt.Y("c:N", sort=None, title=None, axis=alt.Axis(labelLimit=320, grid=False, minExtent=_largura_rotulos(d["c"]))),
                   x=alt.X("v:Q", axis=eixo_v, scale=alt.Scale(padding=90)))
        altura, zero = 40 + 34 * len(d), _zero().encode(x="z:Q")
        barra = alt.Chart(d).mark_bar(size=18, cornerRadiusEnd=4)
        # Valor escrito na ponta de cada barra: o ganho pequeno dos clientes com crédito é o achado, não um defeito.
        texto = dict(y=enc["y"], x="v:Q", text="rotulo:N")
        rotulos = (alt.Chart(d).transform_filter("datum.v >= 0").mark_text(align="left", dx=6, fontSize=12, fontWeight=500, color=NEUTRO)
                   .encode(**texto)
                   + alt.Chart(d).transform_filter("datum.v < 0").mark_text(align="right", dx=-6, fontSize=12, fontWeight=500, color=NEUTRO)
                   .encode(**texto))
        return _estilo((barra.encode(color=COR_SINAL, tooltip=dica, **enc) + rotulos + zero)
                       .properties(height=altura))
    else:
        enc = dict(x=alt.X("c:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, grid=False)),
                   y=alt.Y("v:Q", axis=eixo_v))
        altura, zero = 280, _zero().encode(y="z:Q")
        barra = alt.Chart(d).mark_bar(size=26, cornerRadiusEnd=4)
    return _estilo((barra.encode(color=COR_SINAL, tooltip=dica, **enc) + zero).properties(height=altura))


def _linha(df: pd.DataFrame, r_virada) -> alt.Chart:
    d = df.rename(columns={DIFERENCA: "v"})
    base = alt.Chart(d).encode(
        x=alt.X("r:Q", title="Quanto do preço você mantém", scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%")),
        y=alt.Y("v:Q", axis=alt.Axis(title="Diferença para você (R$)", labelExpr=EIXO_BRL)))
    camadas = (base.mark_line(color=NEUTRO, strokeWidth=2)
               + base.mark_point(filled=True, size=70, opacity=1).encode(
                   color=COR_SINAL, tooltip=[alt.Tooltip("r:Q", title="Preço mantido", format=".0%"),
                                             alt.Tooltip("v:Q", title=DIFERENCA, format=",.2f")])
               + _zero().encode(y="z:Q"))
    if r_virada is not None:   # onde a decisão troca de lado (cálculo exato, modelo.poder_de_preco_indiferenca)
        camadas += alt.Chart(pd.DataFrame({"x": [float(r_virada)]})).mark_rule(
            color=NEUTRO, strokeDash=[4, 4]).encode(x="x:Q")
    return _estilo(camadas.properties(height=280))


# ---------------------------------------------------------------- explicação por IA
def _chave_api() -> str | None:
    try:
        return st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    except Exception:   # sem secrets.toml o Streamlit levanta erro ao ler st.secrets
        return os.environ.get("GEMINI_API_KEY")


def _mostrar_explicacao(saida: dict, fatos, origem: str) -> None:
    from raio_x.explicacao import numeros
    texto = saida["resumo"] + " " + " ".join(c["argumento"] for c in saida["clientes"])
    st.markdown(saida["resumo"])
    with st.expander("Como conversar com cada cliente sobre preço"):
        for c in saida["clientes"]:
            st.markdown(f"**{fatos.nomes[c['id']]}** — {c['argumento']}")
    autoria = "escrito por IA (Gemini), revisado à mão" if saida.get("revisado_em") else "escrito por IA (Gemini)"
    st.caption(f"Texto {autoria} {origem}. Os {len(numeros(texto))} números citados foram conferidos "
               "um a um contra o cálculo: texto com número que não existe no cálculo é descartado.")


def _explicacao_ia() -> None:
    from raio_x.explicacao import ErroExplicacao, gerar, montar_fatos
    _secao(st, "Em linguagem simples", "O que esse resultado quer dizer e como conversar com cada cliente.")
    fatos = montar_fatos(clientes, folha, ano, t, r, k, reducao)
    gravadas = st.session_state.setdefault("_explicacoes", {})
    if fatos.chave in gravadas:
        _mostrar_explicacao(gravadas[fatos.chave], fatos, "nesta sessão")
        return
    arquivo = ler_conferencia(EXPLICACOES) or {}   # mesmo leitor de JSON da conferência
    if fatos.chave in arquivo:
        g = arquivo[fatos.chave]
        quando = dt.datetime.fromisoformat(g["gerado_em"]).strftime("%d/%m/%Y")
        _mostrar_explicacao(g, fatos, f"e gravado em {quando}")
        return
    chave = _chave_api()
    if not chave:
        st.caption("A explicação por IA está gravada para os perfis de exemplo no cenário inicial (2027, 0% do "
                   "preço mantido). Mude o perfil ou volte os controles para vê-la.")
        return
    if st.button("Escrever explicação com IA", icon=":material/edit_note:"):
        from google import genai
        from google.genai import errors
        with st.spinner("Escrevendo e conferindo os números…"):
            try:
                gravadas[fatos.chave] = gerar(genai.Client(api_key=chave), fatos)
            except (ErroExplicacao, errors.APIError) as e:
                st.warning(f"Explicação descartada: {e}")
                return
        _mostrar_explicacao(gravadas[fatos.chave], fatos, "nesta sessão")
    else:
        st.caption("Os nomes dos clientes não são enviados à IA: ela recebe só os números do cálculo, com os "
                   "clientes como C1, C2...")


# ---------------------------------------------------------------- resultado
ganho = res.prestador_h - res.prestador_s
s = res.indiferenca_peso_com_credito
oficial = "referência oficial (TCU)" if ano == 2027 else "cenário, não alíquota oficial"
nb = lambda v: brl(v).replace(" ", "\u00a0")   # "R$" não quebra longe do número
r_pct = pct(r, 0)
r_virada = poder_de_preco_indiferenca(clientes, folha, ano, t, k)
sens = pd.DataFrame(sensibilidade_r(clientes, folha, ano, t, k))
ja_compensa = sens[DIFERENCA].iloc[0] >= 0   # H já vence S mantendo 0% do preço
if ganho > 0:
    veredito = f'Recolher IBS/CBS por fora rende <span class="rx-ganha">{nb(ganho)}</span> a mais por ano.'
elif ganho < 0:
    veredito = (f'Fique no Simples puro. Recolher IBS/CBS por fora custaria '
                f'<span class="rx-perde">{nb(-ganho)}</span> por ano.')
else:
    veredito = "Simples puro e IBS/CBS por fora empatam nessa carteira."
if s is None:
    frase = (f"Mantendo {r_pct} do preço, recolher por fora " + ("ganha" if ganho > 0 else "perde") +
             " do Simples puro em qualquer composição de carteira.")
else:
    frase = (f"Mantendo {r_pct} do preço, recolher por fora só compensa se pelo menos <b>{pct(s, 1)}</b> da sua "
             f"receita vier de clientes que aproveitam o crédito. Hoje são <b>{pct(1 - res.peso_sem_credito, 1)}</b>.")
if ganho < 0 and r_virada is not None:
    frase += f" Com a sua carteira, você precisaria manter pelo menos <b>{pct(r_virada, 0)}</b> do preço."
_topo(" · ".join(x for x in ("Raio-X da Carteira", st.session_state.get("perfil_ativo"),
                                  f"{len(clientes)} clientes", str(ano)) if x), veredito, frase,
      f"CBS + IBS por fora (t) {pct(t)}, {oficial}. {AVISO}")

with area_resultado:
    m = st.columns(4)
    m[0].metric("No Simples puro", brl(res.prestador_s), border=True,
                help="Quanto fica com você em 12 meses, depois do DAS.")
    m[1].metric("Recolhendo por fora", brl(res.prestador_h), delta=brl(ganho), border=True,
                delta_color="blue" if ganho > 0 else ("red" if ganho < 0 else "off"),   # mesma polaridade dos gráficos
                help="Quanto fica com você em 12 meses recolhendo IBS/CBS por fora do DAS, com o preço que você "
                     "consegue manter.")
    m[2].metric("Receita com crédito", pct(1 - res.peso_sem_credito, 1), border=True,
                help="Parte da receita vinda de clientes que aproveitam o crédito de IBS/CBS (empresas do regime "
                     "regular ou do Simples que recolhe por fora).")
    m[3].metric("Preço a manter",
                "já compensa" if ja_compensa else (pct(r_virada, 0) if r_virada is not None else "nenhum"),
                border=True,
                help="Menor parte do preço de hoje que você precisa manter para recolher por fora empatar com o "
                     "Simples puro, nesta carteira e neste ano. \"Nenhum\": nem mantendo 100% compensa.")

    if ano == 2027 and dt.date.today() <= PRAZO_CANCELAMENTO:   # P03
        if ganho < 0:
            st.warning("**Prazo: 20/12/2026.** Se você já optou por recolher IBS/CBS por fora no 1º semestre de "
                       "2027, ainda dá para cancelar a opção. Com estes números, o Simples puro deixa mais "
                       "dinheiro com você: leve isso ao seu contador antes do prazo.", icon=":material/event:")
        else:
            st.info("**Prazos:** a opção por recolher por fora no 1º semestre de 2027 encerrou em 30/10/2026 e "
                    "pode ser cancelada até 20/12/2026; a próxima janela de opção abre em março de 2027.",
                    icon=":material/event:")

    _explicacao_ia()

    _secao(st, "Cliente a cliente",
           f"Azul: recolher por fora te rende dinheiro nesse cliente. Vermelho: te custa, mantendo {r_pct} do preço.")
    tab = pd.DataFrame(tabela_clientes(res, cred))
    st.altair_chart(_barras(tab, "Cliente", DIFERENCA, horizontal=True), width="stretch")
    # Formato brasileiro pelo Styler: a tela mostra o texto formatado e a ordenação usa o número.
    dinheiro = [c for c in tab.columns if c not in ("Cliente", "Aproveita crédito")]
    principais = ["Cliente", "Aproveita crédito", "Preço hoje", DIFERENCA]
    st.dataframe(tab[principais].style.format(brl, subset=["Preço hoje", DIFERENCA]),
                 hide_index=True, width="stretch")
    with st.expander("Ver todas as colunas"):
        st.dataframe(tab.style.format(brl, subset=dinheiro), hide_index=True, width="stretch")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        _secao(st, "E se você conseguir manter mais do preço?",
               "Diferença na carteira inteira, de 0% (o cliente dita o preço) a 100% (você mantém o preço de hoje)."
               + (" A linha tracejada marca onde a decisão troca de lado." if r_virada is not None else ""))
        st.altair_chart(_linha(sens, r_virada), width="stretch")
    with c2:
        try:
            anos_res, virada = linha_do_tempo(clientes, folha, ts, r, k)
            _secao(st, "Linha do tempo 2027–2033",
                   (f"A decisão troca de lado em {virada}. " if virada else "A decisão não troca de lado no período. ")
                   + "De 2028 em diante a alíquota é cenário: o IBS sobe 10/20/30/40% até 2033.")
            lt = pd.DataFrame({"ano": [str(x.ano) for x in anos_res],
                               DIFERENCA: [float(x.prestador_h - x.prestador_s) for x in anos_res]})
            st.altair_chart(_barras(lt, "ano", DIFERENCA), width="stretch")
        except ForaDoEscopo as e:
            st.error(str(e))

with st.expander("Como calculamos"):
    st.markdown(
        "- **Simples puro (S):** IBS/CBS ficam dentro do DAS; o cliente só credita a fatia de IBS/CBS do DAS.\n"
        "- **Por fora (H):** IBS/CBS saem do DAS e são recolhidos à alíquota cheia; o cliente do regime regular "
        "credita tudo (P04, P05, P17).\n"
        "- **Preço mantido (r):** de 0% (preço cai até o cliente pagar o mesmo que no Simples puro) a 100% "
        "(você mantém o preço de hoje).\n"
        f"- **DAS desta carteira:** Anexo {das.anexo} (Fator R {pct(das.fator_r, 1)}), {das.faixa}ª faixa, "
        f"alíquota efetiva {pct(res.a)}; IBS/CBS dentro do DAS {pct(res.c, 3)}"
        + (" ; teto de 5% do ISS aplicado (P16)" if das.teto_iss_aplicado else "") + ".\n"
        f"- **IBS/CBS por fora em {ano}:** {pct(t)}{' com redução de 30%' if reducao else ''}, {oficial} (P13).\n"
        f"- **Premissas usadas:** {', '.join(das.premissas)}, P01, P13, P17. Nenhum número vem de IA.")



@st.cache_data(ttl=30, show_spinner=False)
def _motor_no_ar() -> bool:
    from raio_x.receita import no_ar
    return no_ar()


with st.expander("Conferir no motor oficial da Receita"):
    if _motor_no_ar():
        st.caption("Envia os percentuais de CBS e IBS do DAS à calculadora do Simples da Receita (rodando "
                   "localmente) e compara com o cálculo próprio, numa nota de R$ 10.000.")
        if st.button("Conferir"):
            from raio_x.receita import ClienteReceita, ErroReceita
            try:
                conf = ClienteReceita(timeout=5).conferir_das(das, f"{ano}-03-10", 10_000)
                if conf.ok:
                    st.success(f"Confere: CBS {brl(conf.motor.v_cbs_sn)} e IBS {brl(conf.motor.v_ibs_sn)} "
                               "no motor da Receita.")
                else:
                    st.error("Divergência: " + "; ".join(conf.divergencias))
            except ErroReceita as e:
                st.warning(str(e))
    else:
        doc = ler_conferencia(CONFERENCIA)
        if doc is None:
            st.caption("O motor da Receita não está no ar aqui e não há conferência gravada.")
        else:
            casos = doc["casos"]
            quando = dt.datetime.fromisoformat(doc["gravado_em"]).strftime("%d/%m/%Y")
            st.caption(f"O motor da Receita não roda nesta hospedagem. Conferência gravada em {quando}: "
                       f"{sum(c['confere'] for c in casos)} de {len(casos)} casos conferem, numa nota de R$ 10.000.")
            caso = caso_conferido(doc, das)
            if caso is None:
                st.info("Os percentuais do DAS desta carteira não estão entre os casos gravados.")
            elif caso["confere"]:
                st.success(f"Esta carteira está entre eles: CBS {brl(caso['motor_v_cbs_sn'])} e IBS "
                           f"{brl(caso['motor_v_ibs_sn'])} no motor, iguais ao cálculo próprio.")
            else:
                st.error("Divergência gravada: " + "; ".join(caso["divergencias"]))
            st.dataframe(pd.DataFrame([{
                "Ano": c["ano"], "Receita 12 meses": brl(c["rbt12"]), "Anexo": c["anexo"], "Faixa": c["faixa"],
                "CBS motor": brl(c["motor_v_cbs_sn"]), "CBS próprio": brl(c["proprio_v_cbs_sn"]),
                "IBS motor": brl(c["motor_v_ibs_sn"]), "IBS próprio": brl(c["proprio_v_ibs_sn"]),
                "Confere": "sim" if c["confere"] else "não"} for c in casos]), hide_index=True, width="stretch")

with st.expander("O que o protótipo não calcula"):
    st.markdown(
        "- Efeito de caixa do split payment e do prazo de recebimento (P07, P08).\n"
        "- Imposto de renda do sócio e pró-labore.\n"
        "- Mudança de faixa do Simples causada pelo novo preço em H.\n"
        "- RBT12 acima de R$ 3,6 milhões, mais de uma atividade, tomador no exterior: erro explícito.")
