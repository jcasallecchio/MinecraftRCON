# Histórico de versões

## 1.3.5
- Sincroniza os pacotes oficiais uma vez na primeira inicialização após esta atualização, mesmo que o binário do servidor já esteja na versão mais recente.
- Mantém os pacotes oficiais incluídos no servidor recém-baixado durante as atualizações.
- Restaura do backup apenas pacotes personalizados ausentes na nova distribuição, sem substituir os pacotes oficiais.

## 1.3.4
- Consulta a API oficial de downloads do Minecraft Bedrock para detectar a versão mais recente.
- Baixa e instala a versão automaticamente na inicialização quando ela difere da versão instalada.
