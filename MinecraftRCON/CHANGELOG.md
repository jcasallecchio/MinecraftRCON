# Histórico de versões

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
