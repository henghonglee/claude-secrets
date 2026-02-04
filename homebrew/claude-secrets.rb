class ClaudeSecrets < Formula
  desc "Intelligent secrets proxy for MCP clients"
  homepage "https://github.com/henghonglee/claude-secrets"
  url "https://github.com/henghonglee/claude-secrets/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      To get started:
        ccs init
        ccs config show-mcp  # Shows how to add to your MCP client

      Then start the server:
        ccs serve

      Or run as a background service:
        brew services start claude-secrets

      LLM Configuration:
        By default, claude-secrets uses Ollama at localhost:11434.
        To use a different LLM:
          ccs config set llm.base_url https://api.openai.com/v1
          ccs config set llm.api_key sk-...
          ccs config set llm.model gpt-4o-mini
    EOS
  end

  service do
    run [opt_bin/"ccs", "serve"]
    keep_alive true
    log_path var/"log/claude-secrets.log"
  end

  test do
    system bin/"ccs", "--version"
  end
end
