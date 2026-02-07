# Workflow Definitions

Tento adresar obsahuje YAML workflow definicie pre AudioMason sync wizard.

## Dodavane workflows

### workflow_basic.yaml
**Popis:** Standardny workflow so vsetkymi otazkami  
**Pouzitie:** `python run_wizard.py` (default)

**Kroky:**
- Vyber zdroja z inbox
- Clean inbox? (y/N)
- Publish? (y/N)  
- Wipe ID3? (y/N)
- Clean stage? (Y/n)
- Author (hint z nazvu)
- Title (hint z nazvu)
- Import -> Detect cover -> Convert -> Tag -> Export -> Cleanup

---

### workflow_minimal.yaml
**Popis:** Minimalny workflow bez otazok  
**Pouzitie:** `python run_wizard.py --workflow workflow_sync/workflow_minimal.yaml`

**Kroky:**
- Vyber zdroja
- Author (hint z nazvu)
- Title (hint z nazvu)
- Import -> Convert -> Tag -> Export -> Cleanup stage

**Nastavenia:**
- Vzdy publikuje
- Vzdy cisti stage
- Ziadne otazky na clean_inbox, wipe_id3

---

### workflow_advanced.yaml
**Popis:** Pokrocily workflow s online metadata a vsetkymi funkciami  
**Pouzitie:** `python run_wizard.py --workflow workflow_sync/workflow_advanced.yaml`

**Kroky:**
- Vsetky basic otazky
- Fetch metadata? (y/N)
- Split chapters? (y/N)
- Loudness norm? (y/N)
- Import -> Fetch metadata -> Detect cover -> Convert (s norm/split) -> Tag -> Export -> Cleanup

**Extra funkcie:**
- Google Books / OpenLibrary metadata
- Chapter splitting z M4A/M4B
- Loudness normalization

---

## Vytvorit vlastny workflow

1. Skopiruj existujuci workflow:
```bash
cp workflow_sync/workflow_basic.yaml workflow_sync/my_workflow.yaml
```

2. Uprav podla potreby:
```yaml
workflow:
  name: "Moj Custom Workflow"
  
  preflight_steps:
    # Vymaz kroky ktore nechces
    # Zmen poradie
    # Uprav prompts a defaults
  
  processing_steps:
    # Pridaj/vymaz kroky
    # Nastav conditions
```

3. Spusti:
```bash
python run_wizard.py --workflow workflow_sync/my_workflow.yaml
```

---

## Struktura workflow YAML

```yaml
workflow:
  name: "Nazov"
  description: "Popis"
  
  preflight_steps:      # Otazky pred spracovanim
    - id: step_id       # Unikatne ID
      type: yes_no|input|menu
      enabled: true
      prompt: "Otazka"
      default: hodnota
      
  processing_steps:     # Spracovanie
    - id: step_id
      plugin: plugin_name
      method: method_name
      enabled: true
      description: "Popis"
      condition: "answers.key == value"

verbosity:              # Co zobrazovat
  quiet: [errors]
  normal: [errors, prompts, progress]
  verbose: [...]
  debug: [...]
```

Viac info: `../WORKFLOW_README.md`
