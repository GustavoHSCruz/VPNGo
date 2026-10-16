"""Short, read-only help for each public command."""

from i18n import language


TOPICS = {
    "en-US": {
        "help": "Usage: vpngo help [command]\n"
                "Show all commands, or explain one command and its options.\n"
                "Examples: vpngo help start | vpngo help profile add",
        "profile": "Usage: vpngo profile add <name> <wireguard.conf>\n"
                   "       vpngo profile list\n"
                   "Add or list named WireGuard profiles. The .conf file stays at its original path.",
        "profile add": "Usage: vpngo profile add <name> <wireguard.conf>\n"
                       "  <name>            Name used by start, assign and switch.\n"
                       "  <wireguard.conf>  Existing WireGuard config; its path is saved.",
        "profile list": "Usage: vpngo profile list\n"
                        "List registered VPN profile names.",
        "assign": "Usage: vpngo assign <app> <profile>\n"
                  "Save the profile for future starts; does not launch the app.\n"
                  "  <app>      App name or registered executable.\n"
                  "  <profile>  Registered VPN profile.",
        "start": "Usage: vpngo start <app> [profile]\n"
                 "       vpngo start <executable> <profile> --temp [-d|--detach]\n"
                 "Normal start closes running copies and launches the app on the VPN.\n"
                 "  [profile]  Use this profile and save it; omitted uses the saved profile.\n"
                 "  --temp     Run once without saving or closing other copies.\n"
                 "  -d        Return to the prompt during a temporary run.",
        "--temp": "Usage: vpngo --temp <profile> <executable> [-d|--detach]\n"
                  "Run once without saving an app assignment.\n"
                  "  <profile>     Registered VPN profile.\n"
                  "  <executable>  Absolute/relative path, or name in the current directory or PATH.\n"
                  "  -d, --detach  Return to the prompt; the app keeps running.",
        "detach": "Usage: vpngo --temp <profile> <executable> [-d|--detach]\n"
                  "Detach a temporary run from the original terminal. The VPN session ends when the app exits.",
        "switch": "Usage: vpngo switch <app> <profile>\n"
                  "Change a running app's VPN profile without restarting it.\n"
                  "  <profile>  Registered profile; saved after a successful switch.\n"
                  "The app must reconnect its own connections. Run 'on' first if it is off.",
        "stop": "Usage: vpngo stop <app>\n"
                "Close the app and end its VPN session. The saved profile remains.",
        "status": "Usage: vpngo status <app>\n"
                  "Show the current route and the settings saved for the next start.",
        "on": "Usage: vpngo on <app>\n"
              "Return a managed app to its VPN route. The app stays open.",
        "off": "Usage: vpngo off <app>\n"
               "Move a managed app to the direct route. The app stays open.",
        "policy": "Usage: vpngo policy <app> killswitch|dns on|off\n"
                  "Save Linux routing safeguards for the next start.\n"
                  "  killswitch  Block traffic if the VPN route fails.\n"
                  "  dns         Isolate DNS; requires the kill switch and a DNS IP.\n"
                  "  on|off      Enable or disable the chosen safeguard.\n"
                  "Strict per-app policies are unavailable on macOS and Windows.",
        "policy killswitch": "Usage: vpngo policy <app> killswitch on|off\n"
                             "Block traffic if the VPN route fails. On by default on Linux.\n"
                             "Takes effect on the next start; turn DNS isolation off before disabling it.",
        "policy dns": "Usage: vpngo policy <app> dns on|off\n"
                      "Isolate DNS inside the Linux VPN namespace. Off by default.\n"
                      "Requires the kill switch and an IP in the profile's DNS field.\n"
                      "Takes effect on the next start.",
        "helper": "Usage: vpngo helper add <app> <executable>\n"
                  "Add a helper process to the app's Mihomo route on macOS/Windows.\n"
                  "The executable must exist; the change takes effect on the next start.",
        "helper add": "Usage: vpngo helper add <app> <executable>\n"
                      "Route the helper executable with the app on macOS/Windows.\n"
                      "The executable must exist; the change takes effect on the next start.",
        "config": "Usage: vpngo config <path>\n"
                  "Register an executable, a folder of executables, or a macOS .app bundle.\n"
                  "Use this when the app cannot be found automatically.",
        "version": "Usage: vpngo version\n"
                   "Show the installed version (or 'dev' from a source checkout).",
        "setup": "Usage: vpngo setup <wireguard.conf> [profile]\n"
                 "Legacy form of 'profile add'; omitted profile means 'default'.",
        "profiles": "Usage: vpngo profiles\n"
                    "Legacy form of 'profile list'.",
    },
    "pt-BR": {
        "help": "Uso: vpngo help [comando]\n"
                "Lista os comandos ou explica as opções de um comando.\n"
                "Exemplos: vpngo help start | vpngo help profile add",
        "profile": "Uso: vpngo profile add <nome> <wireguard.conf>\n"
                   "     vpngo profile list\n"
                   "Cadastra ou lista perfis WireGuard. O arquivo .conf fica no caminho original.",
        "profile add": "Uso: vpngo profile add <nome> <wireguard.conf>\n"
                       "  <nome>            Nome usado por start, assign e switch.\n"
                       "  <wireguard.conf>  Configuração existente; o caminho é salvo.",
        "profile list": "Uso: vpngo profile list\n"
                        "Lista os nomes dos perfis VPN cadastrados.",
        "assign": "Uso: vpngo assign <app> <perfil>\n"
                  "Salva o perfil para os próximos starts; não abre o app.\n"
                  "  <app>     Nome do app ou executável cadastrado.\n"
                  "  <perfil>  Perfil VPN cadastrado.",
        "start": "Uso: vpngo start <app> [perfil]\n"
                 "     vpngo start <executável> <perfil> --temp [-d|--detach]\n"
                 "O start normal fecha outras instâncias e abre o app pela VPN.\n"
                 "  [perfil]  Usa e salva esse perfil; sem ele, usa o perfil salvo.\n"
                 "  --temp    Executa uma vez, sem salvar nem fechar outras instâncias.\n"
                 "  -d        Libera o terminal na execução temporária.",
        "--temp": "Uso: vpngo --temp <perfil> <executável> [-d|--detach]\n"
                  "Executa uma vez sem salvar atribuição do app.\n"
                  "  <perfil>      Perfil VPN cadastrado.\n"
                  "  <executável>  Caminho absoluto/relativo, ou nome na pasta atual ou PATH.\n"
                  "  -d, --detach  Libera o terminal; o app continua aberto.",
        "detach": "Uso: vpngo --temp <perfil> <executável> [-d|--detach]\n"
                  "Libera o terminal de origem. A sessão VPN termina quando o app fecha.",
        "switch": "Uso: vpngo switch <app> <perfil>\n"
                  "Troca o perfil VPN de um app aberto sem reiniciá-lo.\n"
                  "  <perfil>  Perfil cadastrado; salvo após a troca funcionar.\n"
                  "O app precisa reconectar. Se estiver em off, execute 'on' primeiro.",
        "stop": "Uso: vpngo stop <app>\n"
                "Fecha o app e a sessão VPN. O perfil salvo permanece.",
        "status": "Uso: vpngo status <app>\n"
                  "Mostra a rota atual e as opções salvas para o próximo start.",
        "on": "Uso: vpngo on <app>\n"
              "Recoloca um app gerenciado na rota VPN sem fechá-lo.",
        "off": "Uso: vpngo off <app>\n"
               "Passa um app gerenciado para a rota direta sem fechá-lo.",
        "policy": "Uso: vpngo policy <app> killswitch|dns on|off\n"
                  "Salva proteções de rota do Linux para o próximo start.\n"
                  "  killswitch  Bloqueia o tráfego se a VPN falhar.\n"
                  "  dns         Isola o DNS; exige kill switch e um IP de DNS.\n"
                  "  on|off      Liga ou desliga a proteção escolhida.\n"
                  "Políticas estritas por app não estão disponíveis no macOS/Windows.",
        "policy killswitch": "Uso: vpngo policy <app> killswitch on|off\n"
                             "Bloqueia o tráfego se a VPN falhar. Ligado por padrão no Linux.\n"
                             "Vale no próximo start; desligue o DNS isolado antes de desligá-lo.",
        "policy dns": "Uso: vpngo policy <app> dns on|off\n"
                      "Isola o DNS no namespace VPN do Linux. Desligado por padrão.\n"
                      "Exige kill switch e um IP no campo DNS do perfil.\n"
                      "Vale no próximo start.",
        "helper": "Uso: vpngo helper add <app> <executável>\n"
                  "Inclui um processo auxiliar na rota Mihomo do app no macOS/Windows.\n"
                  "O executável precisa existir; vale no próximo start.",
        "helper add": "Uso: vpngo helper add <app> <executável>\n"
                      "Roteia o executável auxiliar com o app no macOS/Windows.\n"
                      "O executável precisa existir; vale no próximo start.",
        "config": "Uso: vpngo config <caminho>\n"
                  "Cadastra um executável, uma pasta de executáveis ou um pacote .app do macOS.\n"
                  "Use quando o app não for encontrado automaticamente.",
        "version": "Uso: vpngo version\n"
                   "Mostra a versão instalada (ou 'dev' no código-fonte).",
        "setup": "Uso: vpngo setup <wireguard.conf> [perfil]\n"
                 "Forma antiga de 'profile add'; sem perfil, usa 'default'.",
        "profiles": "Uso: vpngo profiles\n"
                    "Forma antiga de 'profile list'.",
    },
}


ALIASES = {"temp": "--temp", "-d": "detach", "--detach": "detach"}


def get(topic):
    """Return localized help text, or None for an unknown topic."""
    return TOPICS[language()].get(ALIASES.get(topic, topic))
