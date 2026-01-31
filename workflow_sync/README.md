# Workflow Definitions

Tento adresár obsahuje YAML workflow definície pre AudioMason sync wizard.

## Dodávané workflows

### workflow_basic.yaml
**Popis:** Štandardný workflow so všetkými otázkami  
**Použitie:** `python run_wizard.py` (default)

**Kroky:**
- Výber zdroja z inbox
- Clean inbox? (y/N)
- Publish? (y/N)  
- Wipe ID3? (y/N)
- Clean stage? (Y/n)
- Author (hint z názvu)
- Title (hint z názvu)
- Import → Detect cover → Convert → Tag → Export → Cleanup

---

### workflow_minimal.yaml
**Popis:** Minimálny workflow bez otázok  
**Použitie:** `python run_wizard.py --workflow workflow_sync/workflow_minimal.yaml`

**Kroky:**
- Výber zdroja
- Author (hint z názvu)
- Title (hint z názvu)
- Import → Convert → Tag → Export → Cleanup stage

**Nastavenia:**
- Vždy publikuje
- Vždy čistí stage
- Žiadne otázky na clean_inbox, wipe_id3

---

### workflow_advanced.yaml
**Popis:** Pokročilý workflow s online metadata a všetkými funkciami  
**Použitie:** `python run_wizard.py --workflow workflow_sync/workflow_advanced.yaml`

**Kroky:**
- Všetky basic otázky
- Fetch metadata? (y/N)
- Split chapters? (y/N)
- Loudness norm? (y/N)
- Import → Fetch metadata → Detect cover → Convert (s norm/split) → Tag → Export → Cleanup

**Extra funkcie:**
- Google Books / OpenLibrary metadata
- Chapter splitting z M4A/M4B
- Loudness normalization

---

## Vytvoriť vlastný workflow

1. Skopíruj existujúci workflow:
```bash
cp workflow_sync/workflow_basic.yaml workflow_sync/my_workflow.yaml
```

2. Uprav podľa potreby:
```yaml
workflow:
  name: "Moj Custom Workflow"
  
  preflight_steps:
    # Vymaž kroky ktoré nechceš
    # Zmeň poradie
    # Uprav prompts a defaults
  
  processing_steps:
    # Pridaj/vymaž kroky
    # Nastav conditions
```

3. Spusti:
```bash
python run_wizard.py --workflow workflow_sync/my_workflow.yaml
```

---

## Štruktúra workflow YAML

```yaml
workflow:
  name: "Názov"
  description: "Popis"
  
  preflight_steps:      # Otázky pred spracovaním
    - id: step_id       # Unikátne ID
      type: yes_no|input|menu
      enabled: true
      prompt: "Otázka"
      default: hodnota
      
  processing_steps:     # Spracovanie
    - id: step_id
      plugin: plugin_name
      method: method_name
      enabled: true
      description: "Popis"
      condition: "answers.key == value"

verbosity:              # Čo zobrazovať
  quiet: [errors]
  normal: [errors, prompts, progress]
  verbose: [...]
  debug: [...]
```

Viac info: `../WORKFLOW_README.md`
