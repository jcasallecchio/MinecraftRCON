# Acesso pela internet com NetherNet

Este guia parte de um servidor que já funciona na rede local. Se ainda estiver instalando o add-on, comece pelo [guia de instalação e configuração](../MinecraftRCON/DOCS.md).

## 1. Prepare a rede

1. Reserve no roteador o IP local do Home Assistant via DHCP. Neste guia, `192.168.1.50` representa esse IP.
2. Compare o IPv4 WAN mostrado pelo roteador com o IPv4 público da sua conexão. Se o WAN for privado, estiver entre `100.64.0.0` e `100.127.255.255` ou for diferente do IP público, verifique se existe outro roteador à frente ou CGNAT. Com dois roteadores, o encaminhamento precisa funcionar nos dois, a menos que um esteja em modo bridge. Para CGNAT, confirme com o provedor a disponibilidade de um IPv4 público.
3. No arquivo `/share/minecraftRCON/server.properties`, confira `transport=nethernet` e `server-port=19132`. Deixe `server-ip` vazio se o servidor puder escutar em todas as interfaces. Se for editar, pare o add-on, salve o arquivo e inicie novamente.

Use `online-mode=true` e `allow-list=true` para restringir o acesso aos jogadores cadastrados. Mantenha a API RCON (`19133/TCP`) na rede local ou em uma VPN. As regras deste guia são para o jogo. [Guia oficial do Bedrock Dedicated Server](https://help.minecraft.net/hc/en-us/articles/49914677714957)

## 2. Encaminhe as portas no roteador

Abra **Encaminhamento de portas**, geralmente no menu **NAT**, e direcione **TCP 19132 externo → TCP 19132 no IP local do Home Assistant**. Permita a entrada nessa porta no firewall do host, se houver. O jogo usa essa porta TCP para a sinalização inicial. O tráfego da partida usa UDP. Em redes que permitem UDP de saída e o tráfego de retorno, o NetherNet pode negociar portas UDP dinamicamente com `server-udp-ports` vazio. [Guia oficial do NetherNet no Bedrock Dedicated Server](https://help.minecraft.net/hc/en-us/articles/49914677714957)

### Faixa UDP fixa em redes que precisam de encaminhamento

A tabela mostra uma configuração de exemplo para redes em que o encaminhamento UDP precisa usar uma faixa fixa. Crie uma regra TCP para a sinalização e outra regra UDP para a faixa de jogo. Use o IP reservado do Home Assistant. Se houver firewall no host, permita também a faixa UDP local.

| Protocolo | Porta externa | Destino local | Porta interna |
| --- | --- | --- | --- |
| TCP | `19132` | `192.168.1.50` | `19132` |
| UDP | `19140–19155` | `192.168.1.50` | `19140–19155` |

Os nomes e caminhos do menu variam entre fabricantes. Procure funções como **Encaminhamento de portas**, **Port Forwarding**, **Servidor virtual** ou **NAT**. Configure o protocolo, a porta ou faixa externa, o IP local de destino e a porta ou faixa interna. Para o exemplo UDP, encaminhe cada porta externa à porta interna correspondente, de `19140 → 19140` até `19155 → 19155`. Se o seu roteador esconder um campo de porta interna ao escolher uma faixa, confira o manual para saber como representar o mapeamento um a um. Revise as portas salvas para confirmar que a faixa UDP não está sendo enviada inteira para uma única porta interna.

Com o add-on parado, ajuste as propriedades existentes em `/share/minecraftRCON/server.properties` e inicie-o novamente.

~~~properties
transport=nethernet
server-port=19132
server-ip=
server-udp-ports=203.0.113.10:19140-19155:19140-19155
~~~

Troque `203.0.113.10` pelo seu **IPv4 público atual**. Os campos são, em ordem, o IP público, a faixa UDP externa e a faixa UDP interna. Use um IP numérico nesse campo. O domínio fica no endereço de conexão do cliente. A configuração acima foi validada em uma instalação que também tinha uma regra UDP individual em `19132`. Se já tiver essa regra e quiser removê-la, desative somente ela e confirme uma nova entrada de fora da sua rede antes de excluir. [Formato de configuração UDP do Bedrock Dedicated Server](https://help.minecraft.net/hc/en-us/articles/49914677714957)

Como o add-on usa a rede do próprio host, ajuste essas regras no roteador e no firewall da rede. No jogo, os jogadores continuam usando a porta **19132**.

## 3. Configure um nome DNS

DuckDNS e Cloudflare são duas formas de atribuir um nome ao IPv4 público. Você pode usar qualquer uma delas ou manter as duas.

### DuckDNS

1. Entre no [DuckDNS](https://www.duckdns.org/), crie um subdomínio e copie o token da sua conta.
2. No Home Assistant, instale o aplicativo oficial **Duck DNS**. Na aba **Configuração**, use o seu subdomínio completo em `domains` e o token em `token`. Salve e inicie o aplicativo.
3. Confira os logs do Duck DNS e verifique se o registro IPv4 do hostname coincide com o IPv4 público do roteador.

O exemplo abaixo configura apenas a atualização de DNS.

~~~yaml
domains:
  - seu-servidor.duckdns.org
token: "COLE_AQUI_O_TOKEN_DO_DUCKDNS"
aliases: []
seconds: 300
lets_encrypt:
  accept_terms: false
  algo: secp384r1
  certfile: fullchain.pem
  keyfile: privkey.pem
~~~

Se o Duck DNS já estiver configurado para outros serviços, preserve o token, os domínios e as opções de certificado atuais. O Minecraft usa o nome em `domains` e a porta `19132`. [Documentação do aplicativo Duck DNS para Home Assistant](https://github.com/home-assistant/apps/blob/master/duckdns/DOCS.md)

### Cloudflare

1. Abra na Cloudflare uma zona DNS ativa de um domínio seu e vá a **DNS → Registros**.
2. Crie um registro **A**. Use `minecraft` como nome para obter um endereço como `minecraft.example.com`. Informe o **IPv4 público** atual no destino.
3. Em **Status do proxy**, selecione **Somente DNS (DNS only)**, com a nuvem cinza. Salve. O cliente do jogo vai se conectar diretamente ao seu roteador. O encaminhamento de portas da seção anterior continua necessário. [Status do proxy DNS da Cloudflare](https://developers.cloudflare.com/dns/proxy-status/)

### Quando o IPv4 público mudar

O aplicativo Duck DNS atualiza o registro do DuckDNS periodicamente. Se você cadastrou um registro **A** direto na Cloudflare, atualize também esse registro. Se declarou um IPv4 explícito em `server-udp-ports`, atualize-o em `server.properties` e reinicie o add-on. Nesse caso, atualizar o DNS sozinho pode fazer a sinalização voltar a funcionar enquanto o servidor ainda anuncia o IP antigo para UDP.

## 4. Teste de fora da rede

1. No celular, desligue o Wi-Fi e confirme que o 4G/5G está ativo. Use uma versão compatível do Minecraft Bedrock e entre na sua conta Microsoft.
2. Abra **Jogar → Servidores → Adicionar servidor**. No campo **Endereço**, use somente o nome, como `seu-servidor.duckdns.org` ou `minecraft.example.com`. No campo **Porta**, informe `19132`.
3. Confira **Configurações → Geral → opção de dados móveis para jogo on-line** no próprio Minecraft. No Android usado na validação, desativar o uso automático nessa opção e confirmar o uso de dados móveis quando o jogo perguntou permitiu avançar. Se o jogo travar antes de entrar mesmo com dados móveis ativos, reproduza esse ajuste e abra o jogo novamente. O texto da opção e do aviso pode variar por versão.
4. Confirme que entrou de fato no mundo. No Home Assistant, confira o registro da entrada do seu jogador na aba **Logs** ou em `/share/minecraftRCON/server.log`.

### Se a lista mostra o servidor, mas o mundo não abre

| Sintoma | O que conferir |
| --- | --- |
| Funciona no Wi-Fi e fica na tela de voltar ou carregando no 4G/5G | Confira primeiro a opção de dados móveis do próprio Minecraft. Faça uma conexão nova já fora do Wi-Fi. |
| O domínio não resolve ou aponta para outro IP | Compare a resposta de `nslookup seu-servidor.duckdns.org` ou `nslookup minecraft.example.com` com o IPv4 público atual. Na Cloudflare, confira se a nuvem está cinza. |
| O servidor aparece no jogo ou `GET /v1/join` responde HTTP 200, mas a entrada falha | A consulta confirma a sinalização TCP. Confira separadamente a faixa UDP, a correspondência entre portas externas e internas e o IPv4 anunciado, se configurado. |
| O jogo rejeita a entrada | Confira a compatibilidade entre a versão Bedrock do cliente e a do servidor, as permissões de multijogador da conta Microsoft e o Gamertag na lista de jogadores. |

Para conferir só a sinalização TCP a partir de outra rede, use `curl --max-time 5 -i http://minecraft.example.com:19132/v1/join` com seu próprio endereço. Para verificar o UDP, entre no mundo pelo jogo.

Na instalação validada, foi preciso ajustar tanto a opção de dados móveis do Minecraft quanto o encaminhamento UDP do roteador. Depois dos dois ajustes, a entrada no mundo funcionou pelo DuckDNS e pelo domínio na Cloudflare.
