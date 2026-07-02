#!/bin/bash
# Quick setup script for QingDu development environment

set -e

echo "🚀 Setting up QingDu development environment..."

# Create .env from .env.example if it doesn't exist
if [ ! -f .env ]; then
    echo "📋 Creating .env file from .env.example..."
    cp .env.example .env
    # Generate a unique signing key for this installation. .env.example
    # deliberately ships SECRET_KEY empty - a shared key would let anyone
    # forge auth tokens.
    GENERATED_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${GENERATED_KEY}|" .env
    echo "✅ .env file created with a freshly generated SECRET_KEY"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "🐳 You can now start the application with:"
echo "   docker-compose up -d"
echo ""
echo "📚 Or run locally with:"
echo "   pip install -r requirements.txt"
echo "   uvicorn app.main:app --reload"
echo ""
echo "🌐 Application will be available at:"
echo "   http://localhost:8000"
echo ""
echo "🔑 Admin credentials:"
echo "   A random admin password is generated on first startup and"
echo "   written to data/admin_bootstrap.txt (also shown in the logs)."
