# Instalação e configuração

## Pré-requisitos

- Home Assistant OS com Supervisor e loja de aplicativos, também chamada de loja de add-ons.
- Host **x86-64 (amd64)**, espaço livre para o mundo, o download e os backups, e acesso à internet para baixar o servidor dedicado. O add-on executa diretamente o binário Linux oficial do [Bedrock Dedicated Server](https://www.minecraft.net/en-us/download/server/bedrock).
- Minecraft **Bedrock Edition** em versão compatível com a do servidor. Para jogar pela internet, use uma conta Microsoft com permissão de multijogador.

## Instalar e iniciar

1. Abra **Configurações → Aplicativos (ou Add-ons) → Instalar aplicativo**. Abra o menu **⋮ → Repositórios** e adicione `https://github.com/jcasallecchio/MinecraftRCON`. Você também pode usar o [botão My Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjcasallecchio%2FMinecraftRCON).
2. Na loja, selecione **Bedrock Server with RCON** e clique em **Instalar**.
3. Na aba **Configuração**, defina um `rcon_token` aleatório de pelo menos **32 caracteres**. Gere-o com um gerenciador de senhas e guarde-o nele. A tabela abaixo descreve as opções adicionais.
4. Salve, clique em **Iniciar** e acompanhe a aba **Logs**. Na primeira execução, o add-on baixa o Bedrock e prepara os arquivos de configuração. Aguarde a mensagem de que o servidor iniciou.
5. No jogo, entre em **Jogar → Servidores → Adicionar servidor**, informe o **IP local do Home Assistant** no campo Endereço e **19132** no campo Porta. Use um nome de sua escolha no campo Nome do servidor.

Se pretende jogar pela internet, confirme primeiro que consegue entrar no mundo pela rede local. Depois, siga o [guia de portas, DuckDNS e Cloudflare](https://github.com/jcasallecchio/MinecraftRCON/blob/main/docs/acesso-remoto.md).

Se você instalou pelo endereço antigo (`https://github.com/jcasallecchio/homeassistant-addons`), continue usando o add-on já instalado. O Home Assistant gera o identificador a partir da URL cadastrada. Adicionar o endereço novo pode exibir uma segunda entrada para o mesmo add-on. [Como o Home Assistant identifica repositórios](https://contributors.home-assistant.io/apps/guides/repository/#the-repository-id)

## Opções do add-on

| Opção | Padrão | Como usar |
| --- | --- | --- |
| `rcon_token` | Vazio | O add-on exige um token de pelo menos 32 caracteres para iniciar, mesmo se você só for jogar. Use o valor no cabeçalho `Authorization: Bearer` das requisições autenticadas. |
| `rcon_allowed_ips` | Vazio | Lista separada por vírgulas de IPs ou redes que podem acessar a API, por exemplo `192.168.1.20,192.168.1.32/28`. Vazio permite qualquer origem com acesso à porta. O endpoint `/health` é acessível sem token e sem esse filtro. |
| `backup_interval_hours` | `24` | Intervalo em horas para criar backups programados. Aceita de 1 a 720 horas. Use `0` para desativar o agendamento. |
| `backup_keep_count` | `7` | Número de backups mantidos, de 1 a 90. A retenção se aplica aos arquivos gerados tanto pelo agendamento quanto pela API. |

Salve e reinicie o add-on depois de alterar as opções. Guarde o token em um local privado e entregue-o apenas ao serviço que chama a API.

## Configurar o mundo e os jogadores

Os arquivos ficam em `/share/minecraftRCON/`. Use um editor com acesso ao compartilhamento `share`, como o add-on Samba, ou um terminal configurado para acessar esse diretório. Pare o add-on antes de editar os arquivos e inicie-o depois de salvar.

No arquivo `/share/minecraftRCON/server.properties`, altere os valores das propriedades existentes. O exemplo usa o mundo `Meu Mundo` e restringe o acesso à lista de jogadores.

~~~properties
server-name=Meu servidor Bedrock
level-name=Meu Mundo
gamemode=survival
difficulty=normal
online-mode=true
allow-list=true
~~~

Antes de entrar com a lista ativa, adicione o Gamertag de cada jogador. Você pode enviar `allowlist add "Gamertag"` pelo console do Bedrock, inclusive pela [API RCON](#api-rcon), enquanto o servidor estiver rodando. Mantenha `online-mode=true` para autenticar os jogadores pela conta Microsoft.

Para usar um mundo Bedrock existente, faça uma cópia de segurança e, com o add-on parado, copie a pasta do mundo para `/share/minecraftRCON/worlds/`. Em `level-name`, coloque exatamente o nome dessa pasta. O servidor usa `transport=nethernet`, que o add-on garante na inicialização. Consulte as demais propriedades no [guia oficial do Bedrock Dedicated Server](https://help.minecraft.net/hc/en-us/articles/49914677714957).

## API RCON

A API aceita comandos nativos do Bedrock por HTTP e tem como base `http://IP_LOCAL_DO_HOME_ASSISTANT:19133`. Use uma rede de confiança ou VPN. Mantenha essa porta fora do encaminhamento de portas da internet. Configure `rcon_allowed_ips` para limitar as origens que podem usar a API.

| Método e caminho | Função |
| --- | --- |
| `GET /health` | Verifica se a sessão do Bedrock está ativa. Responde `ready` quando disponível e HTTP 503 quando indisponível ou em manutenção. Dispensa token. |
| `GET /api/v1/info` | Mostra a versão da API, o dialeto de comandos e as operações disponíveis. |
| `GET /api/v1/telemetry` | Retorna o estado e a versão do servidor, dados do mundo, jogadores, memória do processo e tempo de atividade. A amostra de jogadores é atualizada em segundo plano a cada 15 segundos e indica sua idade e se está desatualizada. |
| `GET /api/v1/events?after=<id>&limit=<n>` | Retorna eventos de entrada, saída e morte dos jogadores. A API mantém até sete dias e 5.000 eventos. `after` busca eventos posteriores ao cursor e `limit` aceita de 1 a 200. |
| `GET /api/v1/player-stats` | Retorna estatísticas acumuladas por jogador: tempo jogado, sessões, saídas, mortes, primeira atividade e última atividade. Os totais ficam em `/share/minecraftRCON/player_stats.json` sem expiração. |
| `POST /api/v1/commands` | Envia um comando ao console. `POST /rcon` continua disponível para integrações existentes. |
| `GET /backups` | Lista os backups disponíveis para restauração. |
| `POST /backups` | Cria um backup do mundo sob demanda. |
| `POST /backups/<id>/restore` | Restaura o backup indicado. Envie o JSON `{"confirm":"restore <id>"}`, substituindo `<id>` pelo ID exato na URL e no corpo. |

O exemplo abaixo usa a variável de ambiente `RCON_TOKEN` e `192.168.1.50` como IP local de exemplo.

~~~sh
curl --fail-with-body http://192.168.1.50:19133/api/v1/commands \
  -H "Authorization: Bearer ${RCON_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data '{"command":"list"}'
~~~

Envie um comando por requisição, com até 1024 caracteres. A resposta inclui `request_id`, `sent` e, quando disponíveis, linhas recentes do console. A entrega ao console pode ser confirmada pela API. A execução pelo jogo deve ser verificada no mundo ou nos logs. A API limita cada IP a 60 requisições por minuto e 30 comandos por minuto.

Integrações podem usar `edition: "bedrock"` e `command_dialect: "minecraft-bedrock"` para identificar os comandos aceitos. A telemetria inclui `schema_version`, `collected_at`, `server`, `players` e `performance`. O log da API fica em `/share/minecraftRCON/rcon_commands.log` e é rotacionado a cada 2 MiB, com até cinco arquivos anteriores.

O feed de jogadores é lido do log nativo do servidor. Ele armazena apenas entradas, saídas e mensagens de morte, sem registrar mensagens de chat. Os eventos são gravados em `/share/minecraftRCON/player_events.jsonl` e ficam disponíveis no MineDev Console por até sete dias, limitados aos 5.000 eventos mais recentes.

As estatísticas são acumuladas a partir desses eventos e gravadas separadamente em `player_stats.json`, sem a retenção de sete dias do feed. Na primeira inicialização, o add-on aproveita eventos ainda presentes no feed para montar os totais iniciais. O tempo jogado é calculado entre os registros de entrada e saída, e a sessão atual aparece quando há uma amostra recente de jogadores online. Eventos mais antigos que a retenção do feed não podem ser recuperados para compor o histórico inicial.

Use o [MineDev Console](https://github.com/jcasallecchio/MinecraftRCON/tree/main/console) se preferir administrar o servidor por um painel web. O guia do painel explica como configurar o mesmo token da API e usar os comandos, a telemetria e o histórico.

## Backups, restauração e atualizações

- Os backups programados e sob demanda ficam em `/share/minecraftRCON/backups/scheduled/`. Para copiar um mundo em execução, o add-on usa `save hold` e volta a permitir gravações após copiar os dados. Isso requer `allow-cheats=true`. Avalie o impacto nas conquistas antes de ativar cheats em um mundo existente. Consulte a [documentação do comando save](https://learn.microsoft.com/en-us/minecraft/creator/commands/commands/save?view=minecraft-bedrock-stable).
- Antes de restaurar, avise os jogadores e confirme o ID do backup. A restauração encerra o servidor, cria uma cópia para reversão e aplica o backup escolhido. Aguarde a reinicialização e confirme que consegue entrar no mundo.
- A cada inicialização, o add-on consulta a versão oficial do Bedrock. Quando há uma versão diferente, valida o pacote antes de instalar e mantém os mundos e a configuração. Se a consulta ou o download falhar e já houver uma instalação utilizável, o add-on tenta iniciar a versão instalada. A próxima inicialização repete a consulta.
- Mantenha uma cópia do mundo e dos arquivos de configuração em outro dispositivo. O diretório de backups do add-on fica no mesmo armazenamento do servidor.
