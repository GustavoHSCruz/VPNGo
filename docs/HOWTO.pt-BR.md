# Guia passo a passo do vpngo

O vpngo abre um aplicativo que você escolhe, como o Firefox ou o Discord, por uma VPN. Só esse aplicativo usa a VPN; todo o resto do computador continua na sua conexão normal.

Você precisa de:

- um computador com Linux, Windows ou macOS;
- um arquivo de VPN no formato WireGuard (`.conf`). A parte 1 mostra como conseguir um de graça no Proton VPN;
- uns 15 minutos.

Os comandos vão num terminal: o **Terminal** no Linux e no macOS, o **PowerShell** no Windows. Copie cada comando, cole no terminal e aperte Enter. Quando o terminal pedir sua senha, digite e aperte Enter; nada aparece na tela enquanto você digita, e isso é normal.

> **Situação por sistema.** O Linux está testado. Os launchers de Windows e macOS estão prontos, mas ainda não foram testados em computadores reais. Se você usar, um relato ajuda muito (veja a seção [Contributing](../README.md#contributing) do README).

## Conteúdo

1. [Pegue seu arquivo de VPN](#1-pegue-seu-arquivo-de-vpn) (todos os sistemas)
2. [Linux](#2-linux)
3. [Windows](#3-windows)
4. [macOS](#4-macos)
5. [Uso no dia a dia](#5-uso-no-dia-a-dia) (todos os sistemas)
6. [Opções avançadas](#6-opções-avançadas)
7. [Problemas e verificações](#7-problemas-e-verificações)
8. [Onde o vpngo guarda os arquivos](#8-onde-o-vpngo-guarda-os-arquivos)

## 1. Pegue seu arquivo de VPN

O vpngo não cria contas de VPN. Ele usa o arquivo WireGuard que o seu provedor de VPN fornece. Cada arquivo é um **perfil**: uma saída de VPN, normalmente um país.

### Arquivo gratuito do Proton VPN

O vpngo foi feito e testado com esses arquivos.

1. Crie uma conta gratuita em [protonvpn.com](https://protonvpn.com), se ainda não tiver.
2. Entre em [account.protonvpn.com](https://account.protonvpn.com).
3. Abra **Downloads** e desça até **WireGuard configuration**.
4. Digite um nome para o arquivo, como `vpngo-nl`. O Proton lista seus arquivos por esse nome, para você poder revogar um depois.
5. Escolha sua plataforma (**GNU/Linux**, **Windows** ou **macOS**). Deixe as opções como estão; contas gratuitas só podem ligar ou desligar o **VPN Accelerator**.
6. Escolha um servidor da lista gratuita e clique em **Create**. Quando ficar pronto, baixe o arquivo. Ele vai para a pasta **Downloads**, terminando em `.conf`.

Crie um arquivo para cada país que quiser. Tenha em mente:

- O plano gratuito permite pouquíssimas conexões simultâneas (uma, quando este guia foi escrito). Dois aplicativos em dois perfis gratuitos ao mesmo tempo podem falhar. Confira os termos atuais do Proton.
- Arquivos gratuitos só funcionam com servidores gratuitos, e o país fica definido quando você cria o arquivo.
- Se um perfil parar de conectar, a chave pode ter expirado ou sido revogada nessa mesma página. Crie um arquivo novo e cadastre de novo com o mesmo nome.

Guia do próprio Proton: [How to download WireGuard configuration files](https://protonvpn.com/support/wireguard-configurations/).

### Planos pagos e outros provedores

Os planos pagos do Proton usam a mesma página e oferecem mais servidores e conexões. Outros provedores e servidores WireGuard próprios também funcionam se o arquivo passar nestas verificações, que o `vpngo profile add` faz para você:

- `[Interface]` tem `PrivateKey` válida e `Address` que inclui um endereço IPv4.
- Existe exatamente um `[Peer]`, com `PublicKey` válida, `Endpoint` (`host:porta` ou `[IPv6]:porta`) e `AllowedIPs` que inclui `0.0.0.0/0`.
- `DNS` é opcional. O isolamento de DNS no Linux precisa de um IP nesse campo.

OpenVPN, IKEv2 e aplicativos de VPN que não exportam arquivo WireGuard não são suportados. O README tem a [tabela completa dos campos](../README.md#profile-requirements).

## 2. Linux

**Como funciona no Linux:** o vpngo usa o [vopono](https://github.com/jamesmcm/vopono) para dar a cada aplicativo uma rede isolada, com seu próprio túnel de VPN. O kill switch vem ligado: se a VPN cair, o aplicativo fica sem internet em vez de voltar para a sua conexão normal. O vpngo pede sua senha com `sudo` porque criar essa rede isolada exige permissão de administrador.

### Passo 1: Instale o que o vpngo precisa

Use os comandos do seu sistema.

**Arch Linux, CachyOS, Manjaro:**

```sh
sudo pacman -S --needed git python wireguard-tools iproute2 procps-ng iputils nftables
yay -S vopono-bin
```

Se você usa `paru` em vez de `yay`, rode `paru -S vopono-bin`.

**Ubuntu, Debian, Linux Mint, Pop!_OS** (64 bits Intel/AMD):

```sh
sudo apt update
sudo apt install git python3 wireguard-tools iproute2 procps iputils-ping nftables curl
curl -fLO https://github.com/jamesmcm/vopono/releases/download/1.0.2/vopono_1.0.2_amd64.deb
sudo apt install ./vopono_1.0.2_amd64.deb
```

**Fedora:**

```sh
sudo dnf install git python3 wireguard-tools iproute procps-ng iputils nftables
sudo dnf install https://github.com/jamesmcm/vopono/releases/download/1.0.2/vopono_1.0.2_amd64_fedora.rpm
```

Outros sistemas e computadores ARM: instale as mesmas ferramentas pelo seu gerenciador de pacotes e o vopono pela [página de versões dele](https://github.com/jamesmcm/vopono/releases).

Opcional: para usar o [isolamento de DNS](#kill-switch-e-isolamento-de-dns-no-linux) depois, instale também o `bubblewrap` (`sudo pacman -S bubblewrap`, `sudo apt install bubblewrap` ou `sudo dnf install bubblewrap`).

### Passo 2: Baixe e instale o vpngo

```sh
git clone https://github.com/GustavoHSCruz/VPNGo.git ~/VPNGo
~/VPNGo/linux/install.sh
```

O primeiro comando baixa o vpngo para a pasta `VPNGo` na sua pasta pessoal. O segundo é o **instalador do Linux**, `linux/install.sh`. Ele confere se o passo 1 deu certo e cria o comando `vpngo` em `~/.local/bin`. Não muda mais nada no sistema. Mantenha a pasta `~/VPNGo`: o comando roda a partir dela.

Feche o terminal, abra outro e rode `vpngo profile list`. Se a resposta for `No VPN profiles configured.`, a instalação deu certo. Se aparecer `command not found`, o `~/.local/bin` ainda não está no PATH. Saia da sessão e entre de novo, ou adicione com:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # use ~/.zshrc se o seu terminal usa zsh
```

### Passo 3: Cadastre seu arquivo de VPN

Mova o arquivo para uma pasta privada e dê a ele um nome curto, aqui `minhavpn`. Troque `vpngo-nl.conf` pelo nome do seu arquivo:

```sh
mkdir -p ~/.config/wireguard && chmod 700 ~/.config/wireguard
mv ~/Downloads/vpngo-nl.conf ~/.config/wireguard/
chmod 600 ~/.config/wireguard/*.conf
vpngo profile add minhavpn ~/.config/wireguard/vpngo-nl.conf
```

O vpngo guarda o caminho do arquivo, não uma cópia. Não mova nem apague o arquivo depois.

### Passo 4: Abra um aplicativo pela VPN

```sh
vpngo start firefox minhavpn
```

O vpngo pede sua senha, fecha o Firefox se estiver aberto e abre de novo pela VPN. O comando termina na hora e o Firefox continua aberto; pode fechar o terminal. O vpngo lembra que o Firefox usa `minhavpn`, então da próxima vez basta `vpngo start firefox`.

Use o nome de comando do programa: `firefox`, `chromium`, `discord`, `telegram-desktop` e assim por diante. Se o vpngo não encontrar o programa, veja [Aplicativo não encontrado](#aplicativo-não-encontrado).

### Passo 5: Confira se funcionou

Abra [api.ipify.org](https://api.ipify.org) no Firefox e em outro navegador. Os dois números precisam ser diferentes. O Firefox mostra o endereço da VPN; o outro navegador mostra o seu.

### Desligar

- `vpngo off firefox`: o Firefox continua aberto e volta para a sua conexão normal. `vpngo on firefox` coloca de volta na VPN.
- `vpngo stop firefox`: fecha o Firefox e remove a rede de VPN dele. Se você abrir o Firefox normalmente depois, ele usa a sua conexão normal.

## 3. Windows

**Como funciona no Windows:** o vpngo usa o [Mihomo](https://github.com/MetaCubeX/mihomo), um programa gratuito de roteamento. O Mihomo cria um adaptador de rede virtual e manda pela VPN só os programas que você escolher. O Windows pede permissão (a janela "Deseja permitir que este aplicativo faça alterações no seu dispositivo?") quando o Mihomo inicia, porque criar esse adaptador exige permissão de administrador.

Dois limites para saber: não existe kill switch, então se o Mihomo parar, os aplicativos voltam para a sua conexão normal. E um aplicativo que abre programas auxiliares separados pode precisar de [configuração extra](#programas-auxiliares-windows-e-macos).

### Passo 1: Instale o que o vpngo precisa

Abra o **PowerShell**: aperte a tecla Windows, digite `PowerShell` e aperte Enter. Rode estes comandos um de cada vez:

```powershell
winget install -e --id Git.Git
winget install 9NQ7512CXL7T
```

O primeiro comando instala o Git, que baixa o vpngo. O segundo instala o [Python install manager](https://www.python.org/downloads/latest/pymanager/) pela Microsoft Store; o vpngo é escrito em Python. Aceite os termos se o winget perguntar.

Feche o PowerShell, abra de novo e rode `python --version`. Se ele oferecer instalar uma versão do Python, aceite. No fim precisa aparecer `Python 3.` seguido de um número. Se abrir a Microsoft Store em vez disso, instale o **Python install manager** pela Store e tente de novo.

Agora instale o Mihomo. Estes comandos baixam a versão oficial para o seu computador da [página de versões do Mihomo](https://github.com/MetaCubeX/mihomo/releases) e salvam como `mihomo.exe` na pasta `bin` da sua pasta de usuário:

```powershell
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64-compatible' }
New-Item -ItemType Directory -Force "$HOME\bin" | Out-Null
Invoke-WebRequest "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-windows-$arch-v1.19.32.zip" -OutFile "$env:TEMP\mihomo.zip"
Expand-Archive "$env:TEMP\mihomo.zip" "$env:TEMP\mihomo" -Force
Move-Item "$env:TEMP\mihomo\mihomo-windows-$arch.exe" "$HOME\bin\mihomo.exe" -Force
```

O Mihomo já traz o driver do adaptador virtual do Windows (Wintun); não precisa de mais nada. O vpngo foi conferido com o Mihomo v1.19.32. Se você guardar o `mihomo.exe` em outro lugar, defina a variável `VPNGO_MIHOMO` com o caminho completo dele.

### Passo 2: Baixe e instale o vpngo

```powershell
git clone https://github.com/GustavoHSCruz/VPNGo.git "$HOME\VPNGo"
powershell -ExecutionPolicy Bypass -File "$HOME\VPNGo\windows\install.ps1"
```

O primeiro comando baixa o vpngo para a pasta `VPNGo` da sua pasta de usuário (por exemplo `C:\Users\voce\VPNGo`). O segundo roda o **instalador do Windows**, `windows\install.ps1`. O Windows bloqueia scripts por padrão; `-ExecutionPolicy Bypass` libera só esta execução e não muda a configuração para outros scripts. O instalador:

- cria o comando `vpngo` como `vpngo.cmd` em `C:\Users\voce\bin`;
- adiciona essa pasta ao PATH do seu usuário, para o PowerShell e o Prompt de Comando encontrarem o `vpngo` e o `mihomo.exe`.

Ele não precisa de permissão de administrador e não muda mais nada. Mantenha a pasta `VPNGo`: o comando roda a partir dela.

Feche o PowerShell, abra de novo e rode `vpngo profile list`. Se a resposta for `No VPN profiles configured.`, a instalação deu certo.

### Passo 3: Cadastre seu arquivo de VPN

Mova o arquivo para uma pasta dentro da sua pasta de usuário e dê a ele um nome curto, aqui `minhavpn`. Troque `vpngo-nl.conf` pelo nome do seu arquivo:

```powershell
New-Item -ItemType Directory -Force "$HOME\vpn" | Out-Null
Move-Item "$HOME\Downloads\vpngo-nl.conf" "$HOME\vpn\"
vpngo profile add minhavpn "$HOME\vpn\vpngo-nl.conf"
```

O vpngo guarda o caminho do arquivo e prepara a configuração do Mihomo. Não mova nem apague o arquivo depois.

### Passo 4: Abra um aplicativo pela VPN

```powershell
vpngo start firefox minhavpn
```

Na primeira vez, o Windows pede permissão para rodar o Mihomo: clique em **Sim**. Uma janela do Mihomo abre; **deixe ela aberta**, porque fechar tira todos os aplicativos da VPN. Depois o vpngo fecha o Firefox se estiver aberto e abre de novo pela VPN. O vpngo lembra que o Firefox usa `minhavpn`, então da próxima vez basta `vpngo start firefox`.

Use o nome do programa sem `.exe`: `firefox`, `chrome`, `discord` e assim por diante. O vpngo procura em `Program Files`, `Program Files (x86)` e `AppData\Local`. Se não encontrar o programa, veja [Aplicativo não encontrado](#aplicativo-não-encontrado).

### Passo 5: Confira se funcionou

Abra [api.ipify.org](https://api.ipify.org) no Firefox e no Edge. Os dois números precisam ser diferentes. O Firefox mostra o endereço da VPN.

### Desligar

- `vpngo off firefox`: o Firefox continua aberto e volta para a sua conexão normal. `vpngo on firefox` coloca de volta na VPN.
- `vpngo stop firefox`: fecha o Firefox e **bloqueia** a internet dele enquanto o Mihomo estiver rodando. Para abrir de novo com VPN, use `vpngo start firefox`; para usar sem VPN, rode `vpngo off firefox` antes.
- Para desligar tudo, feche a janela do Mihomo. Todos os aplicativos voltam para a sua conexão normal.

## 4. macOS

**Como funciona no macOS:** o vpngo usa o [Mihomo](https://github.com/MetaCubeX/mihomo), um programa gratuito de roteamento. O Mihomo cria uma interface de rede virtual e manda pela VPN só os programas que você escolher. O vpngo pede a senha do seu Mac com `sudo` quando inicia o Mihomo, porque criar essa interface exige permissão de administrador.

Dois limites para saber: não existe kill switch, então se o Mihomo parar, os aplicativos voltam para a sua conexão normal. E um aplicativo que abre programas auxiliares separados pode precisar de [configuração extra](#programas-auxiliares-windows-e-macos).

### Passo 1: Instale o que o vpngo precisa

Abra o **Terminal** (Aplicativos → Utilitários → Terminal) e rode:

```sh
xcode-select --install
```

Uma janela oferece instalar as ferramentas de linha de comando da Apple, que trazem o Git e o Python 3. Clique em **Instalar** e espere terminar. Se o terminal disser que já estão instaladas, siga em frente.

Agora instale o Mihomo. Estes comandos baixam a versão oficial para o seu Mac (Apple Silicon ou Intel) da [página de versões do Mihomo](https://github.com/MetaCubeX/mihomo/releases) e salvam como `mihomo` em `~/.local/bin`:

```sh
arch=$(uname -m | sed 's/x86_64/amd64-compatible/')
mkdir -p ~/.local/bin
curl -fL -o /tmp/mihomo.gz "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-darwin-$arch-v1.19.32.gz"
gunzip -c /tmp/mihomo.gz > ~/.local/bin/mihomo && chmod +x ~/.local/bin/mihomo
```

O vpngo foi conferido com o Mihomo v1.19.32. Se você já usa o [Homebrew](https://brew.sh), `brew install mihomo` também funciona; confira se `brew info mihomo` mostra uma versão recente.

Por fim, garanta que o Terminal encontre os comandos em `~/.local/bin`:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zprofile
```

### Passo 2: Baixe e instale o vpngo

```sh
git clone https://github.com/GustavoHSCruz/VPNGo.git ~/VPNGo
~/VPNGo/macos/install.sh
```

O primeiro comando baixa o vpngo para a pasta `VPNGo` na sua pasta pessoal. O segundo é o **instalador do macOS**, `macos/install.sh`. Ele cria o comando `vpngo` em `~/.local/bin` e não muda mais nada. Mantenha a pasta `~/VPNGo`: o comando roda a partir dela.

Feche o Terminal, abra de novo e rode `vpngo profile list`. Se a resposta for `No VPN profiles configured.`, a instalação deu certo.

### Passo 3: Cadastre seu arquivo de VPN

Mova o arquivo para uma pasta privada e dê a ele um nome curto, aqui `minhavpn`. Troque `vpngo-nl.conf` pelo nome do seu arquivo:

```sh
mkdir -p ~/.config/wireguard && chmod 700 ~/.config/wireguard
mv ~/Downloads/vpngo-nl.conf ~/.config/wireguard/
chmod 600 ~/.config/wireguard/*.conf
vpngo profile add minhavpn ~/.config/wireguard/vpngo-nl.conf
```

O vpngo guarda o caminho do arquivo e prepara a configuração do Mihomo. Não mova nem apague o arquivo depois.

### Passo 4: Abra um aplicativo pela VPN

```sh
vpngo start firefox minhavpn
```

Na primeira vez, o vpngo pede a senha do seu Mac para iniciar o Mihomo, que continua rodando em segundo plano. Depois fecha o Firefox se estiver aberto e abre de novo pela VPN. O vpngo lembra que o Firefox usa `minhavpn`, então da próxima vez basta `vpngo start firefox`.

Use o nome do aplicativo como aparece na pasta Aplicativos, sem `.app`: `firefox`, `discord`, `telegram` e assim por diante. Nomes com espaço vão entre aspas: `vpngo start "google chrome" minhavpn`. Se o vpngo não encontrar o aplicativo, veja [Aplicativo não encontrado](#aplicativo-não-encontrado).

### Passo 5: Confira se funcionou

Abra [api.ipify.org](https://api.ipify.org) no Firefox e no Safari. Os dois números precisam ser diferentes. O Firefox mostra o endereço da VPN.

### Desligar

- `vpngo off firefox`: o Firefox continua aberto e volta para a sua conexão normal. `vpngo on firefox` coloca de volta na VPN.
- `vpngo stop firefox`: fecha o Firefox e **bloqueia** a internet dele enquanto o Mihomo estiver rodando. Para abrir de novo com VPN, use `vpngo start firefox`; para usar sem VPN, rode `vpngo off firefox` antes.
- Para desligar tudo, pare o Mihomo com `sudo pkill -x mihomo`. Todos os aplicativos voltam para a sua conexão normal.

## 5. Uso no dia a dia

Os comandos são os mesmos em todos os sistemas. Troque `app` pelo nome do programa e `perfil` por um nome que você escolheu no `profile add`.

| Comando | O que faz |
| --- | --- |
| `vpngo profile add <perfil> <arquivo.conf>` | Cadastra um arquivo de VPN com um nome, ou atualiza. |
| `vpngo profile list` | Lista seus perfis. |
| `vpngo start <app> [perfil]` | Fecha o aplicativo e abre pela VPN dele. Com um perfil, também guarda essa escolha. |
| `vpngo assign <app> <perfil>` | Muda o perfil que o aplicativo vai usar da próxima vez, sem abrir. |
| `vpngo status <app>` | Mostra se o aplicativo está na VPN e qual perfil usa. |
| `vpngo switch <app> <perfil>` | Passa um aplicativo aberto para outro perfil sem fechar. |
| `vpngo off <app>` / `vpngo on <app>` | Passa um aplicativo aberto para a sua conexão normal, ou de volta para a VPN. |
| `vpngo stop <app>` | Fecha o aplicativo e encerra a sessão de VPN dele. |

Você pode rodar vários aplicativos ao mesmo tempo, cada um no seu perfil:

```sh
vpngo profile add alemanha /caminho/para/de.conf
vpngo profile add brasil /caminho/para/br.conf
vpngo start firefox alemanha
vpngo start discord brasil
vpngo switch firefox brasil
```

**Sobre o `switch`.** Só o aplicativo escolhido muda. As conexões que ele já tinha são fechadas e o próprio aplicativo precisa reconectar. A maioria faz isso em segundos; se algum ficar sem conexão, recarregue a página ou use a opção de reconectar do próprio aplicativo. O `switch` é recusado enquanto o aplicativo estiver em `off`; rode `on` antes.

- **Linux:** o vpngo mantém a rede isolada do aplicativo, troca o túnel de VPN e confere se o túnel novo responde antes de confirmar. Se a conferência falhar, restaura o túnel, os endereços, o MTU, o DNS e a rota anteriores. Num teste real com dois túneis, o mesmo aplicativo continuou rodando enquanto o endereço público mudou. Uma consulta DNS falhou durante a troca e a requisição seguinte se recuperou sem nenhuma ação.
- **Windows e macOS:** o vpngo muda a escolha do Mihomo só para aquele aplicativo e fecha as conexões que o Mihomo atribui a ele.

## 6. Opções avançadas

### Kill switch e isolamento de DNS no Linux

No Linux, todo aplicativo inicia com o kill switch ligado. Você pode mudar isso por aplicativo; a mudança vale no próximo `start`:

```sh
vpngo policy exemplo-app killswitch on
vpngo policy exemplo-app dns on
vpngo start exemplo-app
```

O isolamento de DNS (`dns on`) precisa do `bubblewrap`, do kill switch e de um IP na linha `DNS =` do perfil; os arquivos do Proton têm. Ele faz o aplicativo consultar nomes de sites pelo servidor DNS da VPN em vez do servidor do seu computador. Aplicativos com DNS próprio (DNS sobre HTTPS, por exemplo), ou que passam trabalho para programas fora da rede isolada, ainda podem escapar. Teste o aplicativo antes de depender disso. Para desligar os dois, desligue primeiro o DNS e depois o kill switch.

No Windows e no macOS, `policy ... killswitch on` e `policy ... dns on` são recusados: o Mihomo não consegue garantir isso por aplicativo. Se o Mihomo parar, não identificar um processo ou um programa auxiliar ficar sem regra, o tráfego pode sair pela sua conexão normal.

### Programas auxiliares (Windows e macOS)

No Linux, tudo o que o aplicativo abre fica na rede isolada dele. No Windows e no macOS, o Mihomo reconhece os programas pelo nome, então um programa auxiliar separado que o aplicativo abre (um atualizador, um renderizador, um processo de rede separado) pode usar a sua conexão normal. Cadastre os auxiliares conhecidos:

```sh
vpngo helper add exemplo-app /caminho/completo/do/auxiliar
vpngo start exemplo-app
```

A regra vale no próximo `start`. Ela melhora o reconhecimento, mas não cobre todo processo possível; confira o endereço de dentro do aplicativo quando isso importar.

## 7. Problemas e verificações

### Aplicativo não encontrado

O vpngo procura o programa no PATH, nas pastas que você cadastrou e nas pastas de instalação comuns. Se aparecer `Application 'x' was not found`, diga onde o programa está e tente de novo:

```sh
vpngo config /opt/exemplo-app/bin                      # Linux: a pasta ou o arquivo do programa
vpngo config /Applications/Exemplo.app                 # macOS: o .app
vpngo config "C:\Program Files\Exemplo\exemplo.exe"    # Windows: o .exe
```

### O comando `vpngo` não é reconhecido

Feche o terminal e abra outro. No Linux e no macOS, repita o passo do PATH da instalação do seu sistema. No Windows, confira se `C:\Users\voce\bin\vpngo.cmd` existe; se não existir, rode o instalador de novo.

### Linux

- O `vpngo start` devolve o terminal e o aplicativo continua rodando. Se o aplicativo não abrir, leia o log: `tail -n 30 ~/.local/state/vpngo/start.log`.
- Para comparar endereços pelo terminal, descubra o nome da rede isolada com `vopono status --json` e compare `curl -4 https://api.ipify.org` com `sudo ip netns exec <nome> curl -4 https://api.ipify.org`. O segundo precisa mostrar o endereço da VPN.
- Depois de um `switch`, o status do próprio vopono continua mostrando o servidor de quando o aplicativo iniciou. Confie no `vpngo status <app>` e no endereço observado.
- Se o `switch` disser que a reversão precisa de reparo, não presuma que a rota está segura. Inspecione o snapshot WireGuard indicado e reinicie o aplicativo.

**Teste sem fechar seus aplicativos.** O vpngo traz um programa de teste, o probe, que escreve o endereço público dele no log mais ou menos a cada dez segundos. Troque `minhavpn` e `outra` por dois perfis que você cadastrou:

```sh
vpngo config ~/VPNGo/tests/manual/vpngo-probe
vpngo start vpngo-probe minhavpn
vpngo switch vpngo-probe outra
tail -n 12 ~/.local/state/vpngo/start.log
vpngo stop vpngo-probe
```

Depois do `switch`, o endereço no log precisa mudar para o da nova saída. O probe faz conexões novas a cada vez, então não prova que todo aplicativo reconecta do mesmo jeito. Para testar dois aplicativos ao mesmo tempo, copie o probe com outro nome, por exemplo `cp ~/VPNGo/tests/manual/vpngo-probe ~/.local/state/vpngo/vpngo-probe-b`, cadastre a cópia com `vpngo config` e inicie com outro perfil. Cada cópia escreve o próprio nome antes do endereço.

### Windows

- Rode o vpngo pelo PowerShell ou pelo Prompt de Comando.
- Se o Mihomo não iniciar, leia as mensagens na janela dele e confira `state\config.yaml` na pasta `VPNGo`.
- Se você fechou a janela do Mihomo sem querer, rode `vpngo start <app>` de novo.

### macOS

- O Mihomo continua rodando depois que o comando termina. O log dele fica em `~/VPNGo/state/mihomo.log`.
- Se o vpngo disser `mihomo executable not found`, repita o passo 1 da seção do macOS ou defina `VPNGO_MIHOMO` com o caminho completo do arquivo `mihomo`.

Em todos os sistemas, `vpngo status <app>` mostra a rota atual. Conferir o endereço de dentro do aplicativo é a prova final; no Windows e no macOS, uma regra do Mihomo sozinha não garante que toda conexão do aplicativo use a VPN.

## 8. Onde o vpngo guarda os arquivos

| O quê | Linux e macOS | Windows |
| --- | --- | --- |
| Perfis, caminhos dos aplicativos, escolhas e políticas (`profiles.json`, `apps.json`, `assignments.json`) | `~/.config/vpngo/` | `%APPDATA%\vpngo\` |
| Logs e dados de sessão do Linux | `~/.local/state/vpngo/` | — |
| Configuração e log do Mihomo | `state/` na pasta `VPNGo` | `state\` na pasta `VPNGo` |

Seus arquivos `.conf`, `state/config.yaml` e `state/controller.json` contêm chaves privadas e senhas. Nunca compartilhe nem anexe esses arquivos em relatos de problema.

As mensagens são em inglês por padrão. Para português, defina `VPNGO_LANG=pt-BR` (`$env:VPNGO_LANG = 'pt-BR'` no PowerShell).
