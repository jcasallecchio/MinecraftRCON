<p align="center">
  <img src="MinecraftRCON/icon.png" width="96" alt="Ícone do MinecraftRCON">
</p>

<h1 align="center">MinecraftRCON</h1>

<p align="center">Servidor dedicado de Minecraft Bedrock para Home Assistant OS, com painel web de administração e backups do mundo.</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjcasallecchio%2FMinecraftRCON"><img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Adicionar repositório ao Home Assistant"></a>
</p>

## O que o projeto oferece

- **Servidor Bedrock com NetherNet.** Jogue na rede local ou configure o roteador para receber jogadores pela internet.
- **Atualização na inicialização.** O add-on consulta a versão oficial do Bedrock e mantém a instalação existente se uma falha de download impedir a atualização.
- **Comandos, telemetria e dados de jogadores.** A API HTTP permite enviar comandos ao console, consultar versão, jogadores, memória e tempo de atividade, acompanhar entradas, saídas e mortes e consultar estatísticas acumuladas por jogador.
- **MineDev Console.** Painel web opcional para consultar a telemetria, acompanhar a atividade e comparar tempo de jogo, sessões e mortes, enviar comandos com sugestões e exportar a auditoria.
- **Backups do mundo.** Crie cópias programadas ou sob demanda, com retenção configurável e restauração autenticada.

## Instalação rápida

1. No **Home Assistant OS** em um host **x86-64 (amd64)**, abra **Configurações → Aplicativos (ou Add-ons) → Instalar aplicativo**.
2. No menu **⋮ → Repositórios**, adicione `https://github.com/jcasallecchio/MinecraftRCON`. O botão acima abre essa etapa com o endereço preenchido.
3. Instale **Bedrock Server with RCON**. Na aba **Configuração**, defina um `rcon_token` aleatório com pelo menos 32 caracteres. Salve e inicie o add-on.
4. No Minecraft **Bedrock Edition**, abra **Jogar → Servidores → Adicionar servidor** e use o IP local do Home Assistant na porta **19132**. Confira o primeiro acesso na rede local antes de configurar a internet.

Se você já instalou o add-on pelo endereço antigo do repositório, continue usando a instalação existente. O Home Assistant identifica o add-on pela URL que foi cadastrada.

## Guias

| Guia | O que você encontra |
| --- | --- |
| [Instalação e configuração](MinecraftRCON/DOCS.md) | Primeiro acesso, mundo existente, parâmetros do add-on, API e backups |
| [Acesso pela internet](docs/acesso-remoto.md) | Encaminhamento TCP e UDP, DuckDNS, Cloudflare e teste no 4G/5G |
| [MineDev Console](console/README.md) | Instalação do painel PHP, login, configuração do token, comandos e histórico |
| [Histórico de versões](MinecraftRCON/CHANGELOG.md) | Mudanças por versão do add-on |

> Para jogar fora de casa, libere somente as portas do jogo descritas no guia. Mantenha a API de administração (`19133/TCP`) na rede local ou em uma VPN.

## Suporte e créditos

Ao [abrir uma issue](https://github.com/jcasallecchio/MinecraftRCON/issues/new), informe a versão do add-on, a versão do Bedrock, o modelo do roteador se a falha for de rede e se a conexão é local ou externa. Envie apenas o trecho relevante do log, com tokens e endereços pessoais ocultos.

Baseado no [add-on original de jdeath](https://github.com/jdeath/homeassistant-addons). Código sob a [licença MIT](LICENSE.txt).
