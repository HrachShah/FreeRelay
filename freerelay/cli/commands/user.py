import typer
import uuid
import subprocess
import json
from rich.console import Console
from rich.table import Table
from freerelay.shared.security.crypto import generate_api_key, hash_api_key

console = Console()
user_app = typer.Typer(help="Manage users and API keys")

@user_app.command("create")
def create_user(email: str, tier: str = "free"):
    """Create a new user and a default organization."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    
    try:
        # 1. Create User
        sql_user = f"INSERT INTO users (id, email) VALUES ('{user_id}', '{email}')"
        subprocess.run(["team-db", sql_user], check=True, capture_output=True)
        
        # 2. Create Org
        sql_org = f"INSERT INTO organizations (id, name, tier) VALUES ('{org_id}', '{email}''s Org', '{tier}')"
        subprocess.run(["team-db", sql_org], check=True, capture_output=True)
        
        # 3. Link User to Org
        sql_link = f"INSERT INTO organization_members (id, org_id, user_id, role) VALUES ('{str(uuid.uuid4())}', '{org_id}', '{user_id}', 'owner')"
        subprocess.run(["team-db", sql_link], check=True, capture_output=True)
        
        console.print(f"[green]User and Organization created successfully![/green]")
        console.print(f"User ID: {user_id}")
        console.print(f"Org ID: {org_id}")
        console.print(f"Email: {email}")
        console.print(f"Tier: {tier}")
    except Exception as e:
        console.print(f"[red]Failed to create user: {e}[/red]")

@user_app.command("list")
def list_users():
    """List all users."""
    sql = "SELECT id, email, tier, created_at FROM users"
    try:
        result = subprocess.run(["team-db", sql], capture_output=True, text=True, check=True)
        users = json.loads(result.stdout)
        
        table = Table(title="FreeRelay Users")
        table.add_column("ID", style="dim")
        table.add_column("Email", style="cyan")
        table.add_column("Tier", style="green")
        table.add_column("Created At", style="magenta")
        
        for user in users:
            table.add_row(user["id"], user["email"], user["tier"], user["created_at"])
            
        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list users: {e}[/red]")

@user_app.command("add-key")
def add_key(email: str, label: str = "Default Key"):
    """Generate and add an API key for a user."""
    # Find user
    sql_find = f"SELECT id FROM users WHERE email = '{email}'"
    try:
        res = subprocess.run(["team-db", sql_find], capture_output=True, text=True, check=True)
        users = json.loads(res.stdout)
        if not users:
            console.print(f"[red]User with email {email} not found.[/red]")
            return
        
        user_id = users[0]["id"]
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        key_id = str(uuid.uuid4())
        
        sql_insert = f"INSERT INTO api_keys (id, user_id, key_hash, label) VALUES ('{key_id}', '{user_id}', '{key_hash}', '{label}')"
        subprocess.run(["team-db", sql_insert], check=True, capture_output=True)
        
        console.print(f"[green]API key generated and added![/green]")
        console.print(f"Key: [bold]{api_key}[/bold]")
        console.print(f"Label: {label}")
        console.print("[yellow]Keep this key safe! It won't be shown again.[/yellow]")
        
    except Exception as e:
        console.print(f"[red]Failed to add API key: {e}[/red]")

@user_app.command("usage")
def show_usage(email: str = None):
    """Show usage logs."""
    sql = "SELECT email, provider, model, tokens, cost, savings, usage_logs.created_at FROM usage_logs JOIN users ON usage_logs.user_id = users.id"
    if email:
        sql += f" WHERE email = '{email}'"
    sql += " ORDER BY usage_logs.created_at DESC LIMIT 20"
    
    try:
        result = subprocess.run(["team-db", sql], capture_output=True, text=True, check=True)
        logs = json.loads(result.stdout)
        
        table = Table(title="Recent Usage")
        table.add_column("User", style="cyan")
        table.add_column("Provider/Model", style="white")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost ($)", justify="right")
        table.add_column("Savings ($)", justify="right")
        table.add_column("Time", style="magenta")
        
        for log in logs:
            table.add_row(
                log["email"],
                f"{log['provider']}/{log['model']}",
                str(log["tokens"]),
                f"{log['cost']:.4f}",
                f"{log['savings']:.4f}",
                log["created_at"]
            )
            
        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to show usage: {e}[/red]")
