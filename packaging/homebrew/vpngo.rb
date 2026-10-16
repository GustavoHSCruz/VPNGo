class Vpngo < Formula
  desc "Route selected applications through WireGuard VPN profiles"
  homepage "https://github.com/@REPOSITORY@"
  url "https://github.com/@REPOSITORY@/releases/download/v@VERSION@/vpngo-@VERSION@-macos.tar.gz"
  sha256 "@SHA256_MACOS_TAR_GZ@"
  license "Apache-2.0"

  depends_on "mihomo"
  depends_on :macos

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"macos/vpngo"
  end

  def caveats
    <<~EOS
      vpngo uses the python3 that comes with Apple's command line tools.
      If `python3 --version` asks to install them, accept.

      Step-by-step guide: https://github.com/@REPOSITORY@/blob/v@VERSION@/docs/HOWTO.md#4-macos
    EOS
  end

  test do
    assert_equal "vpngo #{version}", shell_output("#{bin}/vpngo version").strip
  end
end
