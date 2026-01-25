class McpSecrets < Formula
  desc "Intelligent secrets proxy for MCP clients"
  homepage "https://github.com/lightsprint/mcp-secrets"
  url "https://github.com/lightsprint/mcp-secrets/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      To get started:
        mcp-secrets init
        mcp-secrets config show-mcp  # Shows how to add to your MCP client

      Then start the server:
        mcp-secrets serve

      Or run as a background service:
        brew services start mcp-secrets

      LLM Configuration:
        By default, mcp-secrets uses Ollama at localhost:11434.
        To use a different LLM:
          mcp-secrets config set llm.base_url https://api.openai.com/v1
          mcp-secrets config set llm.api_key sk-...
          mcp-secrets config set llm.model gpt-4o-mini
    EOS
  end

  service do
    run [opt_bin/"mcp-secrets", "serve"]
    keep_alive true
    log_path var/"log/mcp-secrets.log"
  end

  test do
    system bin/"mcp-secrets", "--version"
  end
end
