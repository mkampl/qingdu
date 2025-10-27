#!/bin/bash
# Quick setup script for QingDu development environment

set -e

echo "🚀 Setting up QingDu development environment..."

# Create .env from .env.example if it doesn't exist
if [ ! -f .env ]; then
    echo "📋 Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: The default SECRET_KEY is for DEVELOPMENT only!"
    echo "   Generate a new key for production:"
    echo "   python -c \"import secrets; print(secrets.token_urlsafe(32))\""
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
echo "🔑 Default admin credentials:"
echo "   Username: admin"
echo "   Password: admin123"
echo "   (You will be prompted to change on first login)"
