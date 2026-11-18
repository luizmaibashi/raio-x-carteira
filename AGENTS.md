# AGENTS.md — Raio-X da Carteira

Instruções para agentes de IA que trabalham neste repositório. Responda em português (pt-BR).

## O que é

Protótipo para o Hack Brasil 2026: mostra a prestadores de serviço do Simples Nacional que vendem para empresas, cliente a cliente, o efeito da reforma tributária do consumo (IBS/CBS). Prazo de commits: **30/11/2026, 23h59**. Commit depois disso desclassifica.

## Regras que não se negociam

1. **Nenhum número sai de LLM.** Alíquota, imposto, preço e resultado vêm de código determinístico ou das APIs da Receita. O LLM só sugere classificação (com confirmação humana) e escreve explicação; todo número citado por ele é conferido contra o cálculo.
2. **Toda regra tributária cita a premissa** que a sustenta (ID tipo `P14`) num comentário ou campo de dados. Regra sem premissa não entra.
3. **Tabelas legais são geradas por script a partir do texto oficial**, nunca digitadas. O arquivo gerado guarda URL, data de leitura e SHA-256 da fonte.
4. **Fora do escopo retorna erro explícito**, nunca um número aproximado (ex.: RBT12 acima de R$ 3,6 milhões).
5. **Só dado sintético** no repositório e na demo. Nada de CPF, CNPJ ou nota real.
6. **Código de terceiros** (calculadoras da Receita, licença MIT) não é copiado para cá; roda como serviço separado. Se algo for incorporado, o commit cita a fonte.
7. Commits em Conventional Commits, sem coautoria de IA.

## Linguagem do projeto

| Termo | Significado |
|---|---|
| **S** | Simples puro: IBS/CBS dentro do DAS |
| **H** | Simples com IBS/CBS recolhidos por fora (regime regular de IBS/CBS) |
| **a** | alíquota efetiva total do DAS |
| **c** | fatia de CBS + IBS dentro de `a` (`pCBSSN + pIBSSN`) |
| **t** | alíquota nominal de CBS + IBS no regime regular (com redução de 30% quando elegível) |
| **cred** | o cliente toma crédito (1) ou não (0) |
| **r** | poder de preço do prestador, de 0 (cliente indiferente) a 1 (prestador mantém o preço-base) |
| **RBT12** | receita bruta dos 12 meses anteriores |
| **Fator R** | folha dos 12 meses ÷ RBT12; ≥ 28% leva ao Anexo III, abaixo ao Anexo V |
| **carteira** | conjunto de clientes do prestador com o valor faturado de cada um |

## Stack

- Python 3.12+, `pytest`, ambiente em `.venv/`.
- APIs da Receita rodam localmente (Java 21): regime regular na porta 8080, Simples na 8082. O código daqui as chama por HTTP.

## Ordem de trabalho

1. Gerador das tabelas do Simples + módulo DAS, com testes.
2. Modelo econômico S × H (bloqueado até a alíquota de referência de 2027 estar confirmada).
3. Cliente HTTP das APIs da Receita.
4. Entrada de dados (formato ainda em aberto).
5. Classificação assistida por LLM com avaliação; regras de lacuna; explicação.
6. Interface, hospedagem, vídeo.

Teste antes de commit: `pytest` precisa passar.
