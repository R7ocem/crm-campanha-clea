# Deploy no EasyPanel

## DNS

No painel DNS do dominio, crie:

```text
Tipo: A
Nome: cleia45155
Valor: 198.199.73.62
```

O link publico sera:

```text
https://cleia45155.usenexora.com.br/cadastro
```

## App no EasyPanel

Crie um novo servico/app para o CRM, separado do n8n.

Configuracao recomendada:

```text
Tipo: App Docker
Porta interna: 8765
Dominio: cleia45155.usenexora.com.br
HTTPS: ativado pelo EasyPanel
Volume persistente: /data
```

## Variaveis de ambiente

Configure no EasyPanel:

```text
APP_ENV=production
PUBLIC_APP_URL=https://cleia45155.usenexora.com.br
HOST=0.0.0.0
PORT=8765
DATA_DIR=/data
SESSION_MAX_HOURS=12
ADMIN_EMAIL=seu-email-admin
ADMIN_PASSWORD=sua-senha-forte
```

Importante: defina `ADMIN_EMAIL` e `ADMIN_PASSWORD` antes do primeiro deploy com banco vazio. Depois que o banco existe, essas variaveis nao alteram automaticamente o usuario ja criado.

## Depois de publicar

Teste:

- `https://cleia45155.usenexora.com.br`
- `https://cleia45155.usenexora.com.br/cadastro`
- cadastro pelo celular fora do Wi-Fi
- login da equipe
- exportacao CSV

## Backup

O banco fica em:

```text
/data/crm_campanha.sqlite3
```

No EasyPanel/DigitalOcean, mantenha backup do volume `/data`.
