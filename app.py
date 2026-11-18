"""Raio-X da Carteira — tela (Streamlit). Rode: streamlit run app.py"""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from raio_x.das import ForaDoEscopo, calcular
from raio_x.entrada import TOMADORES_CREDITO, ErroEntrada, ler_carteira_csv, ler_linhas_csv
from raio_x.modelo import avaliar_carteira, linha_do_tempo
from raio_x.nfse import ErroNFSe, ler_notas
from raio_x.painel import ANOS, brl, pct, sensibilidade_r, t_por_ano, tabela_clientes

RAIZ = Path(__file__).resolve().parent
EXEMPLO_CSV = RAIZ / "dados" / "exemplos" / "carteira_exemplo.csv"
EXEMPLO_XML = RAIZ / "dados" / "exemplos" / "nfse"
OPCOES_TOMADOR = list(TOMADORES_CREDITO)
ROTULOS_TOMADOR = {"regular": "regular (empresa no regime regular)", "simples_h": "simples_h (Simples com IBS/CBS por fora)",
                   "simples": "simples (Simples puro)", "pf": "pf (pessoa física)", "isento": "isento"}

st.set_page_config(page_title="Raio-X da Carteira", page_icon="🩻", layout="wide")
st.title("Raio-X da Carteira")
st.caption("Reforma tributária para prestador de serviço do Simples Nacional: cliente a cliente, "
           "vale ficar no Simples puro (S) ou recolher IBS/CBS por fora (H)? Protótipo do Hack Brasil 2026, "
           "só com dados sintéticos. Não é consultoria tributária.")


# ---------------------------------------------------------------- entrada
def _df_vazio():
    return pd.DataFrame({"cliente": pd.Series(dtype=str), "valor_12m": pd.Series(dtype=float),
                         "tomador": pd.Series(dtype=str)})


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


if "carteira" not in st.session_state:
    st.session_state.carteira = _df_vazio()
    st.session_state.resumo = ""

with st.sidebar:
    st.header("1. Sua carteira")
    fonte = st.radio("Como entrar com os clientes", ["Exemplo sintético", "CSV", "XMLs de NFS-e"], index=0)
    try:
        if fonte == "Exemplo sintético":
            c1, c2 = st.columns(2)
            if c1.button("Carteira (CSV)", use_container_width=True):
                st.session_state.carteira = _df_de_csv(EXEMPLO_CSV.read_text(encoding="utf-8"))
                st.session_state.resumo = "Carteira sintética de 5 clientes."
            if c2.button("Notas (XML)", use_container_width=True):
                arqs = [(p.name, p.read_bytes()) for p in sorted(EXEMPLO_XML.glob("*.xml"))]
                st.session_state.carteira, st.session_state.resumo = _df_de_xml(arqs)
        elif fonte == "CSV":
            st.caption("Colunas: `cliente;valor_12m;tomador`")
            up = st.file_uploader("Arquivo CSV", type=["csv"])
            if up is not None and st.session_state.get("_csv") != up.file_id:
                st.session_state.carteira = _df_de_csv(up.getvalue().decode("utf-8-sig"))
                st.session_state.resumo, st.session_state._csv = f"{up.name} carregado.", up.file_id
        else:
            ups = st.file_uploader("XMLs das notas emitidas (padrão nacional)", type=["xml"],
                                   accept_multiple_files=True)
            chave = tuple(u.file_id for u in ups)
            if ups and st.session_state.get("_xml") != chave:
                st.session_state.carteira, st.session_state.resumo = _df_de_xml(
                    [(u.name, u.getvalue()) for u in ups])
                st.session_state._xml = chave
    except (ErroEntrada, ErroNFSe) as e:
        st.error(str(e))

    st.header("2. Sua empresa")
    folha = st.number_input("Folha + pró-labore + encargos, 12 meses (R$)", min_value=0.0, value=90_000.0,
                            step=1_000.0, format="%.2f")
    ano = st.selectbox("Ano", ANOS, index=0)
    reducao = st.checkbox("Profissão regulamentada com redução de 30% (ex.: economista, contador)", value=False)
    k = st.number_input("Créditos de IBS/CBS das suas compras em H, 12 meses (R$)", min_value=0.0, value=0.0,
                        step=100.0, format="%.2f")

    st.header("3. Cenário")
    r = st.slider("Seu poder de preço (r)", 0.0, 1.0, 0.0, 0.05,
                  help="0 = o cliente dita o preço e fica indiferente entre S e H; "
                       "1 = você mantém o preço-base e o cliente absorve a mudança.")
    t33 = st.slider("CBS + IBS em 2033 (cenário)", 0.20, 0.32, 0.27, 0.005, format="%.3f",
                    help="Não há alíquota oficial de IBS ainda. O modelo usa estimativas de 26% a 28%. "
                         "Só 2027 (11,3%, TCU) é referência oficial.")

st.subheader("Clientes")
st.caption(st.session_state.resumo or "Escolha uma entrada na barra lateral.")
editada = st.data_editor(
    st.session_state.carteira, num_rows="dynamic", use_container_width=True, hide_index=True,
    column_config={
        "cliente": st.column_config.TextColumn("Cliente", required=True),
        "valor_12m": st.column_config.NumberColumn("Faturado em 12 meses (R$)", min_value=0.0, format="%.2f",
                                                   required=True),
        "tomador": st.column_config.SelectboxColumn("Regime do cliente", options=OPCOES_TOMADOR, required=True,
                                                    help="; ".join(ROTULOS_TOMADOR.values())),
    }, key="editor")

if editada.empty:
    st.info("Carregue a carteira de exemplo na barra lateral para ver o raio-X.")
    st.stop()

faltando = editada[editada["tomador"].isna() | (editada["tomador"].astype(str).str.strip() == "")]
if not faltando.empty:
    st.warning("Informe o regime de: " + ", ".join(faltando["cliente"].astype(str)) +
               ". A nota fiscal não diz se o cliente toma crédito; o protótipo não chuta.")
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
    st.error(f"Fora do escopo do protótipo: {e}")
    st.stop()

# ---------------------------------------------------------------- gráficos
EIXO_BRL = "'R$ ' + replace(format(datum.value, ',.0f'), ',', '.')"
COR_SINAL = alt.condition("datum.v >= 0", alt.value("#2e9e5b"), alt.value("#d9534f"))


def _barras(df: pd.DataFrame, cat: str, val: str, horizontal: bool = False) -> alt.Chart:
    d = df[[cat, val]].rename(columns={cat: "c", val: "v"})
    eixo_v = alt.Axis(title="H − S para você (R$)", labelExpr=EIXO_BRL)
    if horizontal:
        enc = dict(y=alt.Y("c:N", sort=None, title=None, axis=alt.Axis(labelLimit=320)), x=alt.X("v:Q", axis=eixo_v))
        altura = 50 + 36 * len(d)
    else:
        enc = dict(x=alt.X("c:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("v:Q", axis=eixo_v))
        altura = 280
    return alt.Chart(d).mark_bar().encode(
        color=COR_SINAL, tooltip=[alt.Tooltip("c:N", title=cat), alt.Tooltip("v:Q", title=val, format=",.2f")],
        **enc).properties(height=altura)


def _linha(df: pd.DataFrame) -> alt.Chart:
    d = df.rename(columns={"H − S para você": "v"})
    base = alt.Chart(d).encode(
        x=alt.X("r:Q", title="Poder de preço (r)", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("v:Q", axis=alt.Axis(title="H − S para você (R$)", labelExpr=EIXO_BRL)))
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[4, 4], opacity=0.6).encode(y="y:Q")
    return (base.mark_line() + base.mark_point(filled=True).encode(
        color=COR_SINAL, tooltip=[alt.Tooltip("r:Q", format=".2f"), alt.Tooltip("v:Q", title="H − S", format=",.2f")])
            + zero).properties(height=280)


# ---------------------------------------------------------------- resultado
st.divider()
st.subheader(f"Resultado em {ano}")
ganho = res.prestador_h - res.prestador_s
m = st.columns(4)
m[0].metric("Você fica com no Simples puro (S)", brl(res.prestador_s))
m[1].metric("Você fica com IBS/CBS por fora (H)", brl(res.prestador_h), delta=brl(ganho))
m[2].metric("Receita de clientes sem crédito", pct(res.peso_sem_credito, 1))
m[3].metric("Melhor regime para você", res.melhor,
            help="S = Simples puro (IBS/CBS dentro do DAS); H = IBS/CBS recolhidos por fora.")

s = res.indiferenca_peso_com_credito
if s is None:
    frase = ("Com esse poder de preço, H " + ("ganha" if ganho > 0 else "perde") +
             " de S em qualquer composição de carteira.")
else:
    frase = (f"Com r = {r:.2f}, H só compensa se pelo menos **{pct(s, 1)}** da sua receita vier de clientes "
             f"que tomam crédito. Hoje são **{pct(1 - res.peso_sem_credito, 1)}**.")
st.markdown(frase)
st.caption(f"DAS: Anexo {das.anexo} (Fator R {pct(das.fator_r, 1)}), {das.faixa}ª faixa, alíquota efetiva "
           f"{pct(res.a)}; CBS + IBS dentro do DAS (c) {pct(res.c, 3)}. "
           f"CBS + IBS por fora (t) {pct(t)}{' com redução de 30%' if reducao else ''}"
           f"{' — referência oficial (TCU)' if ano == 2027 else ' — cenário, não alíquota oficial'}. "
           f"Premissas: {', '.join(das.premissas)}, P13, P17.")
if das.teto_iss_aplicado:
    st.caption("5ª faixa com teto de 5% do ISS aplicado (P16).")

st.markdown("#### Cliente a cliente")
tab = pd.DataFrame(tabela_clientes(res, cred))
dinheiro = {c: st.column_config.NumberColumn(c, format="R$ %.2f") for c in tab.columns if c not in
            ("Cliente", "Toma crédito")}
st.dataframe(tab, hide_index=True, use_container_width=True, column_config=dinheiro)
st.altair_chart(_barras(tab, "Cliente", "H − S para você", horizontal=True), use_container_width=True)
st.caption("Barras negativas: clientes em que recolher por fora te custa dinheiro com esse poder de preço.")

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### E se você tiver mais poder de preço?")
    sens = pd.DataFrame(sensibilidade_r(clientes, folha, ano, t, k)).set_index("r")
    st.altair_chart(_linha(sens.reset_index()), use_container_width=True)
    st.caption("Diferença H − S na carteira inteira, de r = 0 (cliente dita o preço) a r = 1 (você mantém o preço).")
with c2:
    st.markdown("#### Linha do tempo 2027–2033")
    try:
        anos_res, virada = linha_do_tempo(clientes, folha, ts, r, k)
        lt = pd.DataFrame({"ano": [str(x.ano) for x in anos_res],
                           "H − S para você": [float(x.prestador_h - x.prestador_s) for x in anos_res]}).set_index("ano")
        st.altair_chart(_barras(lt.reset_index(), "ano", "H − S para você"), use_container_width=True)
        st.caption((f"A decisão troca de lado em **{virada}**. " if virada else "A decisão não troca de lado no período. ")
                   + "De 2028 em diante t é cenário (IBS sobe 10/20/30/40% até 2033, P01).")
    except ForaDoEscopo as e:
        st.error(str(e))

with st.expander("Conferir no motor oficial da Receita"):
    st.caption("Envia pCBSSN e pIBSSN à calculadora do Simples da Receita (rodando localmente) e compara com o "
               "cálculo próprio, numa nota de R$ 10.000.")
    if st.button("Conferir"):
        from raio_x.receita import ClienteReceita, ErroReceita
        try:
            conf = ClienteReceita(timeout=5).conferir_das(das, f"{ano}-03-10", 10_000)
            if conf.ok:
                st.success(f"Confere: CBS {brl(conf.motor.v_cbs_sn)} e IBS {brl(conf.motor.v_ibs_sn)} no motor da Receita.")
            else:
                st.error("Divergência: " + "; ".join(conf.divergencias))
        except ErroReceita as e:
            st.warning(str(e))

with st.expander("O que o protótipo não calcula"):
    st.markdown(
        "- Efeito de caixa do split payment e do prazo de recebimento (P07, P08).\n"
        "- Imposto de renda do sócio e pró-labore.\n"
        "- Mudança de faixa do Simples causada pelo novo preço em H.\n"
        "- RBT12 acima de R$ 3,6 milhões, mais de uma atividade, tomador no exterior: erro explícito.\n"
        "- Prazo: quem optou por H no 1º semestre de 2027 pode cancelar até 20/12/2026 (P03).")
