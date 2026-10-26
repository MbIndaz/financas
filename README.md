# Finanças

App multi-utilizador de gestão financeira por envelopes: cada rendimento recebido é repartido por **Despesas** (contas fixas do mês), **Objetivos** (poupanças) e **Para gastar** (o dinheiro livre do dia a dia); os gastos e os pagamentos de contas saem do envelope certo — tudo editável.

- `backend/` — FastAPI + PostgreSQL + Alembic (migrações), JWT multi-user, registo por convite
- `frontend/` — PWA (single-page, sem build step), servida pela própria API
- `docker-compose.yml` — Postgres + API num só comando

A API serve o frontend no mesmo porto (8000), por isso não há URLs para configurar: a app fala com `/api/...` diretamente.

## 1. Correr no teu servidor (o portátil sempre ligado)

Precisas de [Docker](https://docs.docker.com/engine/install/) instalado nesse portátil.

```bash
git clone https://github.com/MbIndaz/financas.git
cd financas
cp backend/.env.example backend/.env
```

Edita `backend/.env`:
- `SECRET_KEY` — qualquer string longa e aleatória (`openssl rand -hex 32`)
- `ADMIN_INVITE_CODE` — o código que TU vais usar para criar a tua própria primeira conta (muda para algo só teu, não deixes o valor de exemplo)
- `DATABASE_URL` já vem certo para o Postgres do docker-compose, não precisas de mexer

```bash
docker compose up -d --build
```

Isto arranca o Postgres, aplica as migrações automaticamente e liga a API em `http://localhost:8000`.

Confirma que está tudo bem:
```bash
docker compose logs -f api
```

## 2. Criar a tua conta

Abre `http://localhost:8000` (ou o IP do portátil na rede local) no browser e regista-te com o `ADMIN_INVITE_CODE` que puseste no `.env`. Depois disso, para convidares outras pessoas, entra em **Definições → Gerar código de convite** dentro da própria app — cada código só serve uma vez.

## 3. Expor com Tailscale Funnel (acesso público grátis, sem mexer no router)

No mesmo portátil (o que corre o Docker):

```bash
# se ainda não tens o Tailscale instalado nesse portátil:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# expõe a app publicamente (Funnel), apontando para o porto 8000 da API:
sudo tailscale funnel 8000
```

O Tailscale dá-te um URL público fixo do género `https://<nome-da-maquina>.<tailnet>.ts.net` — esse é o link que abres no telemóvel e que dás às pessoas que convidares. HTTPS já vem tratado automaticamente.

Para veres o URL exato e confirmar que o Funnel está ativo:
```bash
tailscale funnel status
```

O outro portátil (o que fazes de firewall) não precisa de nenhuma configuração extra — o Funnel liga-se de saída à rede da Tailscale, não abre portas no teu router.

## 4. Instalar no telemóvel

Abre o URL `.ts.net` no Chrome do Android → menu ⋮ → **Adicionar ao ecrã principal**. Fica com ícone próprio, sem barra de endereço, como uma app normal.

## 5. Publicar no GitHub

```bash
git init
git add .
git commit -m "feat: primeira versão da app de finanças multi-user"
```

Cria um repositório vazio `financas` em github.com (sem README), depois:
```bash
git branch -M main
git remote add origin https://github.com/MbIndaz/financas.git
git push -u origin main
```

## Atualizar depois de alterares código

```bash
git pull                          # no portátil-servidor, depois de dares push das alterações
docker compose up -d --build      # reconstrói e aplica novas migrações automaticamente
```

## Criar uma nova migração (quando mudares os modelos em `app/models.py`)

```bash
cd backend
source venv/bin/activate   # ou o teu ambiente Python local
alembic revision --autogenerate -m "descrição da mudança"
```

Revê sempre o ficheiro gerado em `alembic/versions/` antes de correr `docker compose up -d --build` — o autogenerate nem sempre acerta em tudo (renomear colunas, por exemplo).

## Notas de arquitetura

- **Multi-user real**: cada conta só vê os seus próprios dados (rendimentos, gastos, contas, objetivos), reforçado em todas as queries do backend por `user_id`.
- **Registo fechado**: não há registo público — só quem tem um código de convite válido (o `ADMIN_INVITE_CODE` para a tua conta, ou um código gerado por um utilizador existente) consegue criar conta.
- **Saldos derivados, nunca guardados**: os envelopes (`GET /api/summary`) e o saldo de cada objetivo são somas dos movimentos registados (rendimentos com a sua repartição, gastos, pagamentos de contas, depósitos/levantamentos) entre a data do saldo inicial e hoje — editas ou apagas um movimento e tudo recalcula sozinho, sem nada para sincronizar (ver `backend/app/envelopes.py`). Valores em `Numeric(12, 2)`/`Decimal`, sem floats.
