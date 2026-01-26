"""Flask web UI for mcp-secrets management."""

import socket
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, render_template_string, request, redirect, url_for, jsonify

from .vault import Vault

# HTML Templates with embedded CSS
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - MCP Secrets</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            line-height: 1.6;
        }

        .container {
            max-width: 700px;
            margin: 0 auto;
            padding: 40px 20px;
        }

        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 32px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        h1 {
            font-size: 1.75rem;
            font-weight: 600;
            margin-bottom: 24px;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        h1 .icon {
            font-size: 1.5rem;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 8px;
            color: #a0a0a0;
        }

        input[type="text"],
        input[type="password"],
        textarea,
        input[type="datetime-local"] {
            width: 100%;
            padding: 12px 16px;
            font-size: 1rem;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        input:focus,
        textarea:focus {
            outline: none;
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }

        textarea {
            min-height: 80px;
            resize: vertical;
        }

        .password-wrapper {
            position: relative;
        }

        .password-toggle {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: #6366f1;
            cursor: pointer;
            font-size: 0.875rem;
            padding: 4px 8px;
        }

        .password-toggle:hover {
            color: #818cf8;
        }

        .btn-group {
            display: flex;
            gap: 12px;
            margin-top: 28px;
        }

        .btn {
            padding: 12px 24px;
            font-size: 0.875rem;
            font-weight: 500;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .btn-primary {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: #fff;
            flex: 1;
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: #e0e0e0;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.15);
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            padding: 6px 12px;
            font-size: 0.75rem;
        }

        .btn-danger:hover {
            background: rgba(239, 68, 68, 0.3);
        }

        .optional {
            color: #666;
            font-weight: normal;
            font-size: 0.75rem;
        }

        /* Table styles for list view */
        .header-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }

        .secrets-table {
            width: 100%;
            border-collapse: collapse;
        }

        .secrets-table th {
            text-align: left;
            padding: 12px 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #666;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .secrets-table td {
            padding: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            vertical-align: top;
        }

        .secrets-table tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        .secret-name {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
            font-weight: 600;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .copy-btn {
            background: none;
            border: none;
            color: #6366f1;
            cursor: pointer;
            font-size: 0.75rem;
            padding: 2px 6px;
            border-radius: 4px;
            opacity: 0.7;
        }

        .copy-btn:hover {
            opacity: 1;
            background: rgba(99, 102, 241, 0.2);
        }

        .secret-desc {
            color: #a0a0a0;
            font-size: 0.875rem;
            max-width: 300px;
        }

        .status-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .status-valid {
            background: rgba(34, 197, 94, 0.2);
            color: #4ade80;
        }

        .status-expiring {
            background: rgba(234, 179, 8, 0.2);
            color: #facc15;
        }

        .status-expired {
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
        }

        .empty-state {
            text-align: center;
            padding: 48px 24px;
            color: #666;
        }

        .empty-state .icon {
            font-size: 3rem;
            margin-bottom: 16px;
        }

        .alert {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.875rem;
        }

        .alert-success {
            background: rgba(34, 197, 94, 0.2);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }

        .alert-error {
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .actions-cell {
            white-space: nowrap;
        }

        @media (max-width: 600px) {
            .container {
                padding: 20px 16px;
            }

            .card {
                padding: 24px 20px;
            }

            .btn-group {
                flex-direction: column;
            }

            .secrets-table th:nth-child(2),
            .secrets-table td:nth-child(2) {
                display: none;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
    {% block scripts %}{% endblock %}
</body>
</html>
"""

ADD_SECRET_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h1><span class="icon">🔐</span> Add Secret</h1>

    {% if error %}
    <div class="alert alert-error">{{ error }}</div>
    {% endif %}

    <form method="POST" id="add-form">
        <div class="form-group">
            <label for="name">Name</label>
            <input type="text" id="name" name="name" placeholder="e.g., AWS_API_KEY"
                   pattern="[A-Z0-9_]+" title="Use uppercase letters, numbers, and underscores"
                   value="{{ prefill_name or '' }}" required autofocus>
        </div>

        <div class="form-group">
            <label for="value">Secret Value</label>
            <div class="password-wrapper">
                <input type="password" id="value" name="value" placeholder="Enter secret value" required>
                <button type="button" class="password-toggle" onclick="togglePassword()">Show</button>
            </div>
        </div>

        <div class="form-group">
            <label for="description">Description</label>
            <textarea id="description" name="description"
                      placeholder="Help AI assistants understand what this secret is for...">{{ prefill_desc or '' }}</textarea>
        </div>

        <div class="form-group">
            <label for="expires_at">Expiration <span class="optional">(optional)</span></label>
            <input type="datetime-local" id="expires_at" name="expires_at">
        </div>

        <div class="btn-group">
            <button type="button" class="btn btn-secondary" onclick="window.close()">Cancel</button>
            <button type="submit" class="btn btn-primary">Save Secret</button>
        </div>
    </form>
</div>
{% endblock %}

{% block scripts %}
<script>
    function togglePassword() {
        const input = document.getElementById('value');
        const btn = document.querySelector('.password-toggle');
        if (input.type === 'password') {
            input.type = 'text';
            btn.textContent = 'Hide';
        } else {
            input.type = 'password';
            btn.textContent = 'Show';
        }
    }

    // Auto-uppercase the name field
    document.getElementById('name').addEventListener('input', function(e) {
        e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_');
    });
</script>
{% endblock %}
"""

SUCCESS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card" style="text-align: center;">
    <h1 style="justify-content: center;"><span class="icon">✓</span> Secret Added</h1>
    <p style="color: #a0a0a0; margin-bottom: 24px;">
        <strong style="color: #fff;">{{ name }}</strong> has been saved to your vault.
    </p>
    <p style="font-size: 0.875rem; color: #666;">This tab will close automatically...</p>
</div>
{% endblock %}

{% block scripts %}
<script>
    setTimeout(function() {
        window.close();
    }, 1500);
</script>
{% endblock %}
"""

LIST_SECRETS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <div class="header-row">
        <h1><span class="icon">🔑</span> Secrets Vault</h1>
        <a href="{{ url_for('add_secret_form') }}" class="btn btn-primary" style="flex: none;">+ Add New</a>
    </div>

    {% if message %}
    <div class="alert alert-success">{{ message }}</div>
    {% endif %}

    {% if secrets %}
    <table class="secrets-table">
        <thead>
            <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Status</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {% for secret in secrets %}
            <tr>
                <td>
                    <div class="secret-name">
                        {{ secret.name }}
                        <button class="copy-btn" onclick="copyToClipboard('{{ secret.name }}')" title="Copy name">📋</button>
                    </div>
                </td>
                <td class="secret-desc">{{ secret.description[:50] }}{% if secret.description|length > 50 %}...{% endif %}</td>
                <td>
                    {% if secret.status == 'expired' %}
                    <span class="status-badge status-expired">Expired</span>
                    {% elif secret.status == 'expiring' %}
                    <span class="status-badge status-expiring">{{ secret.time_left }}</span>
                    {% else %}
                    <span class="status-badge status-valid">Valid</span>
                    {% endif %}
                </td>
                <td class="actions-cell">
                    <form method="POST" action="{{ url_for('delete_secret', name=secret.name) }}" style="display: inline;"
                          onsubmit="return confirm('Delete {{ secret.name }}?')">
                        <button type="submit" class="btn btn-danger">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty-state">
        <div class="icon">🔐</div>
        <p>No secrets stored yet.</p>
        <p style="margin-top: 8px;"><a href="{{ url_for('add_secret_form') }}" style="color: #6366f1;">Add your first secret</a></p>
    </div>
    {% endif %}
</div>
{% endblock %}

{% block scripts %}
<script>
    function copyToClipboard(text) {
        navigator.clipboard.writeText('{{' + text + '}}').then(function() {
            // Brief visual feedback could be added here
        });
    }
</script>
{% endblock %}
"""


def find_available_port(preferred: int = 5789) -> int:
    """Find an available port, starting with preferred."""
    # Try preferred port first
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', preferred))
            return preferred
    except OSError:
        pass

    # Fall back to OS-assigned port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def create_app(vault: Optional[Vault] = None) -> Flask:
    """Create Flask application."""
    app = Flask(__name__)
    app.secret_key = 'mcp-secrets-webui-session-key'

    # Use provided vault or create new one
    _vault = vault or Vault()

    @app.template_global()
    def render_base():
        return BASE_TEMPLATE

    # Custom template rendering to support inheritance with strings
    def render_with_base(template_str: str, **context):
        """Render a template string that extends base template."""
        # Simple approach: render base with content block replaced
        full_template = BASE_TEMPLATE.replace(
            '{% block content %}{% endblock %}',
            template_str.split('{% block content %}')[1].split('{% endblock %}')[0] if '{% block content %}' in template_str else template_str
        )

        # Handle scripts block
        if '{% block scripts %}' in template_str:
            scripts = template_str.split('{% block scripts %}')[1].split('{% endblock %}')[0]
            full_template = full_template.replace('{% block scripts %}{% endblock %}', scripts)
        else:
            full_template = full_template.replace('{% block scripts %}{% endblock %}', '')

        return render_template_string(full_template, **context)

    @app.route('/add', methods=['GET'])
    def add_secret_form():
        """Display add secret form."""
        prefill_name = request.args.get('name', '')
        prefill_desc = request.args.get('description', '')
        return render_with_base(ADD_SECRET_TEMPLATE,
                               title="Add Secret",
                               prefill_name=prefill_name,
                               prefill_desc=prefill_desc,
                               error=None)

    @app.route('/add', methods=['POST'])
    def add_secret_submit():
        """Handle add secret form submission."""
        name = request.form.get('name', '').strip().upper().replace(' ', '_')
        value = request.form.get('value', '').strip()
        description = request.form.get('description', '').strip()
        expires_at = request.form.get('expires_at', '').strip()

        # Validate
        if not name:
            return render_with_base(ADD_SECRET_TEMPLATE,
                                   title="Add Secret",
                                   prefill_name=name,
                                   prefill_desc=description,
                                   error="Secret name is required")

        if not value:
            return render_with_base(ADD_SECRET_TEMPLATE,
                                   title="Add Secret",
                                   prefill_name=name,
                                   prefill_desc=description,
                                   error="Secret value is required")

        # Convert datetime-local to ISO format
        expires_iso = None
        if expires_at:
            try:
                # datetime-local gives us "YYYY-MM-DDTHH:MM"
                dt = datetime.fromisoformat(expires_at)
                expires_iso = dt.isoformat()
            except ValueError:
                pass

        # Save to vault
        try:
            _vault.load()
            _vault.add(name, value, description, expires_at=expires_iso)
            return render_with_base(SUCCESS_TEMPLATE, title="Success", name=name)
        except Exception as e:
            return render_with_base(ADD_SECRET_TEMPLATE,
                                   title="Add Secret",
                                   prefill_name=name,
                                   prefill_desc=description,
                                   error=f"Failed to save: {e}")

    @app.route('/list')
    def list_secrets():
        """Display all secrets."""
        message = request.args.get('message', '')

        try:
            _vault.load()
            raw_secrets = _vault.list_all(include_expired=True)

            # Process secrets for display
            secrets = []
            for s in raw_secrets:
                secret_info = {
                    'name': s.name,
                    'description': s.description or '(no description)',
                    'status': 'valid',
                    'time_left': ''
                }

                if s.expires_at:
                    try:
                        exp = datetime.fromisoformat(s.expires_at.replace("Z", "+00:00"))
                        now = datetime.now(exp.tzinfo)

                        if exp < now:
                            secret_info['status'] = 'expired'
                        else:
                            delta = exp - now
                            hours = delta.total_seconds() / 3600

                            if hours < 24:
                                secret_info['status'] = 'expiring'
                                if hours < 1:
                                    minutes = int(delta.total_seconds() / 60)
                                    secret_info['time_left'] = f"{minutes}m left"
                                else:
                                    secret_info['time_left'] = f"{int(hours)}h left"
                    except (ValueError, TypeError):
                        pass

                secrets.append(secret_info)

            return render_with_base(LIST_SECRETS_TEMPLATE,
                                   title="Secrets Vault",
                                   secrets=secrets,
                                   message=message)
        except Exception as e:
            return render_with_base(LIST_SECRETS_TEMPLATE,
                                   title="Secrets Vault",
                                   secrets=[],
                                   message=f"Error loading vault: {e}")

    @app.route('/delete/<name>', methods=['POST'])
    def delete_secret(name: str):
        """Delete a secret."""
        try:
            _vault.load()
            if _vault.remove(name):
                return redirect(url_for('list_secrets', message=f"Deleted {name}"))
            else:
                return redirect(url_for('list_secrets', message=f"Secret {name} not found"))
        except Exception as e:
            return redirect(url_for('list_secrets', message=f"Error: {e}"))

    return app


class WebUIServer:
    """Manages the Flask web UI server."""

    def __init__(self, vault: Optional[Vault] = None):
        self.vault = vault or Vault()
        self.app = create_app(self.vault)
        self.port: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None

    def start(self) -> str:
        """Start the web server in a background thread. Returns the URL."""
        if self._thread is not None and self._thread.is_alive():
            return f"http://127.0.0.1:{self.port}"

        self.port = find_available_port()

        def run_server():
            # Use werkzeug server directly for cleaner shutdown
            from werkzeug.serving import make_server
            self._server = make_server('127.0.0.1', self.port, self.app, threaded=True)
            self._server.serve_forever()

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        """Stop the web server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None

    @property
    def url(self) -> Optional[str]:
        """Get the server URL if running."""
        if self.port:
            return f"http://127.0.0.1:{self.port}"
        return None
