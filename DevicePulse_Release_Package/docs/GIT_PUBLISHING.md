# Publish to GitHub/Git

Create a new private repository named `DevicePulse` (recommended until security review is complete). From this folder:

```bash
git init
git add .gitignore README.md CONTRIBUTING.md install.sh release.sh docker-compose.yml .env.example backend dashboard android docs scripts
git status --short
# Carefully confirm .env, APKs, keystores, tokens and customer data are NOT staged.
git commit -m "Initial DevicePulse MVP release package"
git branch -M main
git remote add origin https://github.com/YOUR-ORG/DevicePulse.git
git push -u origin main
```

Replace the remote URL with the repository you actually create. Do not commit `.env`. The generated APK is ignored by `.gitignore`; attach a reviewed signed release APK to a GitHub Release only after the release checklist is complete. Never publish a debug APK as a production artifact.
