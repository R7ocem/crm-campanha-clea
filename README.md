# CRM Campanha 2026

CRM web simples para operacao de campanha eleitoral no Distrito Federal.

## Como abrir

1. Execute `iniciar_crm.bat`.
2. Abra `http://127.0.0.1:8765` no navegador.
3. Entre com as credenciais iniciais locais:
   - email: `admin@campanha.local`
   - senha: `admin123`

Essas credenciais nao aparecem mais na tela de login. Troque a senha antes de uso real em producao.

## Link publico de auto cadastro

No computador local, o formulario publico fica em:

`http://127.0.0.1:8765/cadastro`

Quando o sistema for colocado online, o link para enviar para as pessoas sera:

`https://seu-dominio-ou-link/cadastro`

Em producao, configure `PUBLIC_APP_URL=https://seu-dominio-ou-link`, `APP_ENV=production`, `ADMIN_EMAIL` e `ADMIN_PASSWORD` antes de criar o primeiro banco. Assim o CRM copia o link publico correto, usa cookies seguros e nao depende das credenciais locais de teste.

Esse formulario nao mostra o painel interno. Ele apenas recebe cadastro voluntario com nome, telefone/WhatsApp, regiao administrativa, origem informada, consentimento, apoio declarado voluntariamente e interesse em voluntariado.

Os cadastros entram no CRM com origem `auto cadastro` e passam a contar automaticamente no dashboard. Se o telefone ja existir, o sistema nao cria duplicidade.

Tambem sao suportados links com rastreamento:

- `/cadastro?source=instagram`
- `/cadastro?source=whatsapp`
- `/cadastro?source=evento&event=1`
- `/cadastro?ref=CODIGO`
- parametros UTM: `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`

Depois do cadastro, a pessoa vai para `/cadastro/sucesso`, recebe um link pessoal de indicacao e pode copiar, compartilhar, enviar por WhatsApp ou usar QR Code.

## O que ja esta pronto

- Login com senha criptografada.
- Tela de login sem exibicao de usuario/senha inicial.
- Sessao com expiracao, cookie httpOnly/SameSite e modo `Secure` em producao.
- Rate limit no login e registro de tentativas suspeitas.
- Banco SQLite local.
- Link publico `/cadastro` para auto cadastro.
- Pagina `/cadastro/sucesso` com link pessoal e QR Code.
- Pagina `/privacidade`.
- Referral code automatico para cada contato.
- Rastreamento de origem, UTM, evento e indicacao.
- Rate limiting e honeypot no endpoint publico.
- Cadastro rapido de contatos.
- Prevencao de duplicado por telefone.
- Consentimento para comunicacao.
- Status do relacionamento com historico.
- Marcacao de voluntario, lideranca, sindico, comerciante, associacao e multiplicador.
- Indicacao Contato A -> Contato B.
- Eventos/acoes de rua.
- Associacao de contatos a eventos.
- Sidebar profissional com Visao Geral, Operacao, Crescimento, Gestao e Administracao.
- Dashboard reorganizado como painel de comando: atencao hoje, ritmo da campanha, principais indicadores, evolucao, aquisicao, participacao e territorio.
- Graficos e indicadores calculados do banco, sem inventar numeros.
- Paginas internas para Indicacoes, Origens, Relatorios e Configuracoes.
- Metas operacionais com realizado, percentual, projecao e ritmo necessario.
- Alertas de gestao classificados e limitados para nao gerar ruido em base vazia.
- Resumo do Dia.
- Aba Equipe para criar usuarios internos.
- Exportacao CSV de contatos.

## Banco

As tabelas principais sao: `users`, `contacts`, `contact_history`, `referrals`, `events`, `event_contacts`, `regions`, `goals` e `activities`.

O sistema nao coleta CPF, titulo de eleitor ou documentos.

## Backup antes de producao

- Fazer copia do arquivo `crm_campanha.sqlite3` diariamente enquanto a operacao estiver ativa.
- Manter pelo menos 7 backups diarios e 4 backups semanais.
- Antes de usar em producao, testar restauracao em uma copia local: parar o servidor, substituir o banco por um backup, iniciar o CRM e conferir login, contatos e dashboard.
- Nao considerar backup valido sem testar restauracao.
