# Rede neural da Ejota

Sistema fechado que lê os projetos em andamento (ClickUp) e os documentos de cada
projeto (Google Drive) e gera, para o diretor de projetos e comercial, um relatório
que explica **por que** cada projeto atrasou, com a evidência citada (documento e trecho).

> **Estado atual:** o aplicativo roda com dados **fictícios**. Os dados reais
> (ClickUp e Drive) já foram testados com o projeto EJ 26-127 a partir de uma cópia
> local, que nunca vai para o git. A leitura direta pelas APIs é a Etapa 7.

## Abrir no navegador com um clique (GitHub Codespaces)

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/justnobody0/aa?quickstart=1)

1. Clique no botão acima (logado no GitHub) e em **Create codespace**.
2. Espere de 2 a 3 minutos: o sistema é instalado e o aplicativo sobe sozinho.
3. Uma aba abre com o aplicativo. Se não abrir, vá na aba **Portas** (Ports) e clique no globo da porta 8000.
4. O login aparece no terminal: usuário `diretor` e a senha gerada na primeira vez
   (ela fica no arquivo `.senha-local`, que não vai para o git). Para ver de novo: `bash scripts/acesso.sh`.

O endereço só abre para quem está logado na conta do GitHub dona do Codespace.
O Codespace para sozinho depois de 30 minutos sem uso. Para voltar, abra o mesmo link:
ele reaproveita o que já existe. A conta pessoal tem 60 horas grátis por mês.

## Como rodar no seu computador ou servidor

### Opção A: Docker (recomendado)

```bash
cp .env.example .env
docker compose run --rm ejota python -m ejota.cli hash-password   # cole o hash em EJOTA_PASSWORD_HASH='...'
docker compose run --rm ejota python -m ejota.cli secret-key      # cole em EJOTA_SECRET_KEY
docker compose up -d --build
```

Abra **http://localhost:8000** no navegador e entre com o usuário `diretor` e a senha escolhida.

### Opção B: Python local (3.11+)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ia]"
cp .env.example .env            # preencha hash da senha e chave, como acima
uvicorn ejota.main:app --reload
pytest                          # roda os testes
```

## O que a página mostra

- **Visão geral**: projetos atrasados, causa principal de cada um com nível de confiança
  e a principal evidência, comparação entre projetos, causas por categoria e tempo médio em cada status.
- **Detalhe do projeto**: todas as causas (principal e secundárias), cada citação com link
  para o documento, tabela de tarefas (situação, dias de atraso, dias por status) e lacunas de dados.
- **Exportação**: HTML único (abre offline), CSV (abre no Excel/Sheets) e "Imprimir / PDF".

## Regras

| Situação da tarefa | Conta como atraso? |
|---|---|
| Prazo vencido e status "a fazer" ou "em andamento" | Sim |
| "Validado" depois do prazo | Sim (se a EJ entregou no prazo, aparece "atraso na validação do cliente") |
| "Finalizado" depois do prazo | Sim |
| "Finalizado" dentro do prazo, cliente ainda não validou | Não: aparece como "aguardando validação do cliente" |
| Sem prazo | Não: aparece como lacuna de dado |
| Nome "Msg 1" a "Msg 28" ou "TESTE" | Ignorada |

O prazo do **projeto** vem do Termo de Abertura do Projeto (TAP), na linha "Prazo final do projeto: dd/mm/aaaa".

## Como a causa é gerada (sem inventar)

1. O atraso é calculado **em código**, nunca pela IA (`ejota/engine/delays.py`).
2. Os documentos viram trechos com ID (`901-ata#1`), por seção e por LA (`ejota/documents/chunker.py`).
3. Um analisador propõe causas e citações:
   - `heuristica` (padrão): palavras-chave, sem IA e sem custo;
   - `claude`: API do Claude com saída em JSON validado e dados **pseudonimizados**
     (cliente, valores, e-mails, CPF/CNPJ trocados por marcadores antes do envio).
4. **Verificador** (`ejota/analysis/verify.py`): a citação precisa existir literalmente no trecho;
   se não existir, é descartada. Sem citação válida, a causa vira **"sem evidência"**.
5. A confiança é calculada por regra: **alta** (2 ou mais documentos), **média** (1 documento
   com vários trechos ou apoio do ClickUp), **baixa** (um único trecho).

## Segurança e LGPD

- Login de usuário único com senha em hash argon2 e bloqueio após 5 tentativas.
  O cookie de sessão é `SameSite=Strict` e `Secure` em produção.
- Segredos apenas em variáveis de ambiente (`.env`, que não vai para o git).
- Somente leitura: o cliente HTTP dos conectores bloqueia POST/PUT/PATCH/DELETE (`readonly_http.py`).
  O Drive usará o escopo `drive.readonly`.
- Logs sem dados de clientes: só códigos de projeto e contagens, com filtro que mascara
  nomes após "EJ 26-XXX |", valores em R$, e-mails e CPF/CNPJ.
- O contêiner roda sem root, com sistema de arquivos somente leitura, e só escuta em `127.0.0.1`.

## Estrutura

```
ejota/
  config.py            configuração por variáveis de ambiente
  domain.py            modelo de dados (já prevê Consultor e Necessidade p/ fases futuras)
  connectors/          fontes de dados: fictícia (pronta), ClickUp e Drive (Etapa 7)
  engine/delays.py     regras de atraso, tempo em status, lacunas
  documents/           quebra de documentos em trechos citáveis
  analysis/            heurística, Claude, pseudonimização, verificador
  report/              montagem do relatório e CSV
  templates/, static/  páginas web
  data/fake/           projetos e documentos fictícios
tests/                 testes automáticos
```

## Próximas etapas

7. Conectores reais (ClickUp e Drive somente leitura) testados com respostas gravadas.
8. Um projeto real, **com autorização da diretoria**.
9. Todos os projetos e deploy (servidor a definir; tudo já está em contêiner).

Fases futuras (fora do MVP): grafo visual, formulário de necessidade e repertório de consultores.
