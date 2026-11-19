# Histórico de versões

## 1.6.0
- Adiciona feed persistente de entrada, saída e morte de jogadores, com retenção de sete dias.
- Publica os eventos pela API autenticada `/api/v1/events` e atualiza o MineDev Console automaticamente.
- Permite filtrar o feed por jogador ou consultar a atividade geral.

## 1.5.0
- Adiciona API versionada para integração do Bedrock com o futuro console, incluindo capacidades, telemetria e execução de comandos.
- Publica telemetria de versão, estado, mundo, jogadores, tempo ligado e memória do processo Bedrock.

## 1.4.1
- Corrige a busca de `backup_manager` durante a recuperação de restaurações interrompidas na inicialização.

## 1.4.0
- Usa journal transacional com rollback para recuperar atualizações de arquivos interrompidas.
- Monitora a sessão do Bedrock continuamente, reinicia o servidor com atraso progressivo e faz encerramento seguro do addon.
- Retorna linhas recentes do console como resultado best-effort, com identificador de requisição e sem alegar confirmação de execução.
- Adiciona allowlist opcional de IP/CIDR e limites de frequência à API RCON.
- Cria backups programados e manuais do mundo, com retenção configurável e restauração autenticada com confirmação explícita.
- Adiciona testes automatizados e fixa as dependências Python.

## 1.3.9
- Inicia a versão instalada quando o download, a validação ou a extração do pacote de atualização falhar; tenta novamente na próxima reinicialização.
- Garante `transport=nethernet` no `server.properties` antes de iniciar o Bedrock.

## 1.3.8
- Inicia a versão instalada se a API oficial estiver temporariamente indisponível e tenta novamente na próxima reinicialização.
- Baixa o ZIP para um arquivo temporário, valida integridade e caminhos, e extrai em staging antes de instalar.
- Identifica pacotes oficiais pelo UUID do manifesto e evita copiá-los para os backups de pacotes personalizados.
- Rotaciona os logs do RCON e esclarece que a resposta confirma somente o envio do comando à entrada do servidor.

## 1.3.7
- Permite concluir a atualização do addon mesmo quando `rcon_token` ainda não foi configurado.
- No boot, registra um erro claro e encerra antes de atualizar ou iniciar o servidor se o token estiver ausente ou tiver menos de 32 caracteres.

## 1.3.6
- Exige token Bearer de pelo menos 32 caracteres para enviar comandos RCON.
- Envia comandos ao `screen` sem shell e valida formato, tamanho e caracteres de controle.
- Aguarda a confirmação de inicialização do Bedrock e verifica o endpoint de saúde do RCON antes de informar que estão prontos.

## 1.3.5
- Sincroniza os pacotes oficiais uma vez na primeira inicialização após esta atualização, mesmo que o binário do servidor já esteja na versão mais recente.
- Mantém os pacotes oficiais incluídos no servidor recém-baixado durante as atualizações.
- Restaura do backup apenas pacotes personalizados ausentes na nova distribuição, sem substituir os pacotes oficiais.

## 1.3.4
- Consulta a API oficial de downloads do Minecraft Bedrock para detectar a versão mais recente.
- Baixa e instala a versão automaticamente na inicialização quando ela difere da versão instalada.
