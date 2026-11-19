# Bedrock Server with RCON

Hospede um servidor dedicado de Minecraft Bedrock no Home Assistant OS. O add-on baixa o servidor oficial, verifica atualizações na inicialização e fornece uma API HTTP para comandos, telemetria e backups do mundo.

- **Primeiro acesso.** Configure um token aleatório com pelo menos 32 caracteres em `rcon_token`, inicie o add-on e conecte o jogo ao IP local do Home Assistant na porta **19132**.
- **Jogo pela internet.** Configure o encaminhamento de portas do NetherNet e, se quiser um nome fixo, use DuckDNS ou um registro DNS na Cloudflare.
- **Administração.** A API fica na porta **19133/TCP**. Permita acesso somente pela rede de confiança ou por uma VPN.

Consulte a aba **Documentação** ou o [guia de instalação e configuração no GitHub](https://github.com/jcasallecchio/MinecraftRCON/blob/main/MinecraftRCON/DOCS.md). Para jogar fora de casa, siga o [guia de acesso pela internet](https://github.com/jcasallecchio/MinecraftRCON/blob/main/docs/acesso-remoto.md).
