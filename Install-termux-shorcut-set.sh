#!/data/data/com.termux/files/usr/bin/bash

# Vérifier si termux-setup-storage a été exécuté, sinon le faire
if [ ! -d "/storage/emulated/0" ]; then
    echo "Configuration du stockage Android..."
    termux-setup-storage
    echo "Le stockage Android a été configuré."
else
    echo "Le stockage est déjà configuré."
fi

# Mettre à jour les paquets et installer les dépendances nécessaires
echo "Mise à jour de Termux et installation de Python, pip et git..."
pkg update && pkg upgrade -y
pkg install python git -y
pip install --upgrade pip

pip install requests 

# Télécharger le fichier Python Anime-dowload-termux.py depuis GitHub
echo "Téléchargement du fichier Anime-dowload-termux.py depuis GitHub..."
curl -L -o ~/Scan-dowload-termux.py https://raw.githubusercontent.com/Bicode-dev/Scan_Co-Sama_download/refs/heads/main/CO-SAMA.py

# Créer le répertoire de raccourcis s'il n'existe pas
mkdir -p ~/.shortcuts

# Créer le fichier shell pour exécuter le script Python
cat << 'EOF' > ~/.shortcuts/Scan-dowload-termux.sh
#!/data/data/com.termux/files/usr/bin/bash
cd ~
python3 Scan-dowload-termux.py
EOF

# Rendre le fichier shell exécutable
chmod +x ~/.shortcuts/Scan-dowload-termux.sh

echo "Le script a été créé dans le répertoire des raccourcis !"
