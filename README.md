# Raio-X da Carteira

Protótipo para o Hack Brasil 2026 (trilha Pagamentos e finanças).

Mostra a prestadores de serviço do Simples Nacional que vendem para empresas, cliente a cliente, o impacto da reforma tributária do consumo (IBS/CBS): quanto da receita está em risco, em que preço a decisão muda e quais lacunas do negócio a reforma expõe.

Os cálculos de IBS/CBS usam as calculadoras de código aberto da Receita Federal ([regime regular](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular) e [Simples Nacional](https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional), licença MIT).

> Em construção. Simulação educativa: não substitui a análise de um contador.

## Rodar

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/streamlit run app.py
```

A tela abre com uma carteira sintética de exemplo (CSV) e notas sintéticas de NFS-e (XML).

## Como funciona

| Módulo | O que faz |
|---|---|
| `scripts/gerar_anexos.py` | Gera `dados/anexos_simples.json` a partir do texto oficial dos Anexos III e V (com URL, data e SHA-256 da fonte) |
| `raio_x/das.py` | Fator R, faixa, alíquota efetiva do DAS, partilha de CBS/IBS e teto de 5% do ISS |
| `raio_x/modelo.py` | Compara Simples puro (S) e IBS/CBS por fora (H), cliente a cliente, com poder de preço `r` |
| `raio_x/entrada.py`, `raio_x/nfse.py` | Carteira em CSV ou a partir dos XMLs de NFS-e (CPF descartado na leitura) |
| `raio_x/receita.py` | Confere o cálculo no motor oficial da Receita, rodando como serviço separado |
| `app.py` | Tela em Streamlit |

Nenhum número sai de LLM: todo valor vem de código determinístico ou do motor da Receita, e cada regra cita a premissa que a sustenta.

## Testes

```bash
.venv/bin/pytest
```

Os testes de integração com as calculadoras da Receita (portas 8080 e 8082) são pulados se elas não estiverem no ar.
