# 🚀 Git Setup Instructions

## 📦 **Máš audiomason2.zip**

Tento súbor obsahuje kompletný git repository!

---

## 🎯 **Ako ho pushnúť na GitHub:**

### **1. Rozbaľ ZIP na svojom Macu**

```bash
unzip audiomason2.zip
cd audiomason2-git
```

---

### **2. Skontroluj že je git repo inicializovaný**

```bash
git status
```

Malo by ukázať:
```
On branch master
nothing to commit, working tree clean
```

✅ **Git repo je ready!**

---

### **3. Pridaj remote (GitHub)**

```bash
git remote add origin https://github.com/michalholes/audiomason2.git
```

---

### **4. Push na GitHub**

```bash
# Ak existuje origin, zmeň branch name
git branch -M main

# Push všetko
git push -u origin main
```

---

### **5. Hotovo!** 🎉

Tvoj repozitár je na GitHub:
```
https://github.com/michalholes/audiomason2
```

---

## 📋 **Štruktúra repozitára:**

```
audiomason2/
├── README.md                 # GitHub homepage
├── .gitignore               # Git ignore file
├── audiomason               # Main executable
├── pyproject.toml           # Python config
├── pytest.ini               # Test config
│
├── src/audiomason/          # Source code
│   ├── core/               # Core modules
│   ├── api/                # REST API
│   └── checkpoint/         # Resume support
│
├── plugins/                # Plugin system
│   ├── audio_processor/
│   ├── cli/
│   ├── web_server/
│   └── ...
│
├── pipelines/              # YAML pipelines
│   ├── minimal.yaml
│   └── standard.yaml
│
├── tests/                  # Test suite
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
└── docs/                   # Documentation
    ├── QUICKSTART.md
    ├── COMPLETE.md
    ├── ADVANCED_FEATURES.md
    ├── WEB_SERVER.md
    └── MASTER_SUMMARY.md
```

---

## 🔧 **Nasledujúce kroky po pushu:**

### **1. Pridaj LICENSE**

Na GitHub, vytvor súbor `LICENSE`:
- Klikni "Add file" → "Create new file"
- Názov: `LICENSE`
- Vyber "MIT License"
- Commit

### **2. Pridaj Topics (tagy)**

Na GitHub repo page:
- Klikni na ⚙️ (Settings)
- Pridaj topics: `audiobook`, `python`, `ffmpeg`, `cli`, `web-ui`

### **3. GitHub Actions (optional)**

Vytvor `.github/workflows/tests.yml` pre auto-testing.

### **4. Releases**

Keď je hotové, vytvor Release:
- Tag: `v2.0.0`
- Title: "AudioMason v2.0.0 - First Release"
- Upload `audiomason_2.0.0-1_all.deb` (keď bude)

---

## 📝 **Git Commands - Cheatsheet:**

```bash
# Status
git status

# Add new files
git add .

# Commit
git commit -m "Add new feature"

# Push
git push

# Pull
git pull

# New branch
git checkout -b feature/new-wizard

# Switch branch
git checkout main

# Merge
git merge feature/new-wizard
```

---

## 🎯 **Pre development:**

```bash
# Clone repo (na inom počítači)
git clone https://github.com/michalholes/audiomason2.git
cd audiomason2

# Install
pip install -e ".[all]"

# Test
pytest

# Run
./audiomason process book.m4a
```

---

## 📊 **Repository je ready pre:**

- ✅ GitHub public repo
- ✅ Collaboration
- ✅ Issues & Pull Requests
- ✅ GitHub Actions (CI/CD)
- ✅ GitHub Pages (docs)
- ✅ Releases & Downloads

---

## 🎉 **Hotovo!**

Máš **production-ready git repository** pripravený na push!

**Happy coding!** 🚀
