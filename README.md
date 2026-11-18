# Raio-X da Carteira

**Para o prestador de serviço do Simples que vende para empresas: vale a pena recolher IBS/CBS por fora do DAS? A resposta sai cliente a cliente, e toda conta pode ser conferida.**

Hack Brasil 2026 · trilha Pagamentos e finanças

- **Demo:** https://raio-x-carteira.streamlit.app (abre com dados sintéticos, sem login e sem instalar nada)
- **Vídeo (3 min):** _link a incluir_

> Simulação educativa com dados sintéticos: não substitui a análise de um contador.

## O problema

A partir de 2027, quem contrata um prestador do Simples Nacional só aproveita como crédito a parte de IBS/CBS que está dentro do DAS, uma fatia pequena. Para dar crédito cheio ao cliente, o prestador pode recolher IBS/CBS por fora, pelo regime regular, sem sair do Simples. Só que aí ele paga mais imposto. A opção é semestral, e quem já optou para o 1º semestre de 2027 pode cancelar até **20/12/2026**.

Se compensa ou não, depende de quem são os clientes: empresa do regime regular usa o crédito; empresa do Simples puro e pessoa física, não. Mais de 70% das empresas do Simples vendem para outras empresas, segundo o estudo *Raio-X do Simples Nacional em 2025*, do IBPT ([InfoMoney, 28/08/2025](https://www.infomoney.com.br/business/reforma-tributaria-expoe-fragilidades-do-simples-nacional-no-modelo-b2b-diz-estudo/)). As calculadoras que existem comparam regimes para a empresa inteira. O Raio-X olha **cada cliente**.

## O que a demo mostra

Três prestadores sintéticos, com respostas diferentes (2027, sem repassar nada do imposto ao preço):

| Perfil | Faturamento | Receita de clientes que usam crédito | Resultado |
|---|---|---|---|
| Designer | R$ 300 mil | 76,7% (precisa de 98,9%) | Fica no Simples puro: por fora custaria **R$ 5.450,83/ano**. A conta vira se ela mantiver 57% do preço |
| Consultora de TI | R$ 420 mil | 100,0% | Por fora rende **R$ 503,15/ano**, mas depende de um cliente que responde por 42,9% da receita |
| Contador (redução de 30%) | R$ 312 mil | 96,2% (precisa de 98,3%) | Fica no Simples puro por **R$ 365,61/ano**; a conta vira mantendo 8% do preço |

Para cada carteira, a tela mostra:

- **Veredito** e quanto fica com o prestador em cada regime.
- **Cliente a cliente:** quem rende e quem custa se ele recolher por fora.
- **Preço a manter:** quanto do preço de hoje o prestador precisa segurar para a troca compensar. É o número que ele leva para a negociação.
- **Linha do tempo de 2027 a 2033**, com a alíquota de 2028 em diante como cenário explícito.
- **Pontos de atenção** por regra determinística: receita concentrada num cliente e imposto que vence antes do recebimento.
- **Em linguagem simples:** explicação e o que dizer a cada cliente, escritas por IA, com todos os números conferidos.

A carteira entra de três formas: exemplo pronto, CSV ou os XMLs das notas fiscais de serviço (NFS-e, padrão nacional). Na leitura dos XMLs, o CPF é descartado.

## Por que dá para confiar nos números

1. **Nenhum número sai de LLM.** Alíquota, imposto e resultado vêm de código determinístico. A IA só escreve texto: recebe os números já calculados, com os clientes trocados por C1, C2…, e [um verificador](raio_x/explicacao.py) confere cada número citado. Texto com número que não existe no cálculo é descartado.
2. **Tabelas da lei geradas por script.** [`scripts/gerar_anexos.py`](scripts/gerar_anexos.py) lê os Anexos III e V do Simples Nacional no texto oficial publicado pelo Senado e grava URL, data e SHA-256 da fonte. O gerador falha se uma linha da partilha não somar 100%.
3. **Conferência com o motor oficial.** O cálculo é conferido nas [calculadoras de código aberto da Receita Federal](https://github.com/ReceitaFederal) (licença MIT), que rodam como serviço separado: 19 de 19 casos conferem. Na nuvem, a tela mostra essa conferência gravada.
4. **Toda regra cita uma premissa** (P01 a P21), com fonte legal, data de consulta e grau de certeza.
5. **Fora do escopo dá erro, não número aproximado.** Exemplo: receita acima de R$ 3,6 milhões.
6. **113 testes automatizados**, incluindo testes da tela.

## Arquitetura

| Módulo | O que faz |
|---|---|
| `scripts/gerar_anexos.py` → `dados/anexos_simples.json` | Tabelas do Simples (faixas e partilha de 2027 a 2033) extraídas do texto oficial |
| `raio_x/das.py` | Fator R, faixa, alíquota efetiva do DAS, parte de CBS/IBS dentro do DAS e teto de 5% do ISS |
| `raio_x/modelo.py` | Simples puro × IBS/CBS por fora, por cliente e na carteira; ponto de indiferença; preço a manter |
| `raio_x/lacunas.py` | Pontos de atenção por regra (concentração P20, prazo de recebimento P21) |
| `raio_x/explicacao.py` | Fatos para a IA (Gemini), verificador de números, duas tentativas e depois descarta |
| `raio_x/entrada.py`, `raio_x/nfse.py` | Carteira por CSV ou XML de NFS-e |
| `raio_x/receita.py`, `scripts/gravar_conferencia.py` | Cliente HTTP do motor da Receita e conferência gravada |
| `app.py` | Tela em Streamlit |
| `.github/workflows/manter_demo.yml` | Mantém a demo acordada no Streamlit Community Cloud |

Python 3.12, Streamlit, Altair, `google-genai`. Os textos da IA para os perfis de exemplo ficam gravados em `dados/explicacoes_ia.json` (o original da IA e a revisão humana), e a demo pública não chama a API.

## Rodar localmente

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/streamlit run app.py
.venv/bin/pytest
```

Os testes de integração com as calculadoras da Receita (portas 8080 e 8082) são pulados se elas não estiverem no ar. Para gerar explicações novas: `GEMINI_API_KEY=... python scripts/gerar_explicacoes.py`.

## Limites conhecidos

- A faixa do Simples não é recalculada quando o preço muda com o recolhimento por fora.
- O efeito no caixa do split payment e do prazo de recebimento aparece como alerta, não como número.
- Alíquotas de 2028 em diante são cenário, porque ainda não há alíquota oficial de IBS.
- Ainda ficam de fora: cláusula de repasse em contrato, a elegibilidade à redução de 30% (depende de registro em conselho) e a revisão de um contador.

## Licença

MIT. As calculadoras da Receita Federal não estão copiadas aqui: rodam como serviço separado.
