# wkhtmltopdf — Server Setup

**Why:** The generic PDF service ([`core/services/pdf_service.py`](../../core/services/pdf_service.py), used by the CRM Tax Invoice Summary in `crm.module_maintenance.invoice_sync`) and Frappe's own print/PDF download feature both render HTML to PDF via the `wkhtmltopdf` binary. It is **not** a Python package — it won't show up in `pyproject.toml` or get installed by `bench setup requirements` — it's a separate system binary that must be installed on the server directly.

**Required version:** `0.12.6` **"with patched Qt"**. This matters: the unpatched/distro-packaged build (e.g. plain `apt install wkhtmltopdf`) ignores margins and zoom settings, and the invoice layout will render shrunk/misaligned. Always install the patched build from the official releases below, never from a generic OS package repo.

---

## 1. Check if it's already installed

```bash
wkhtmltopdf -V
```

Expected output:
```
wkhtmltopdf 0.12.6 (with patched qt)
```

If this already prints and includes `(with patched qt)`, nothing to do.

If you get `command not found`, or the version prints **without** `(with patched qt)`, follow the install steps below (installing again will replace a bad build).

---

## 2. Identify the server's OS and architecture

```bash
cat /etc/os-release | grep -E "^(ID|VERSION_CODENAME)="
uname -m
```

Match the output to a package below. All packages come from the project's official release archive: **`wkhtmltopdf/packaging`** on GitHub, release `0.12.6.1-3`.

| OS | Codename | `uname -m` | Package |
|---|---|---|---|
| Ubuntu 22.04 | jammy | `x86_64` | `wkhtmltox_0.12.6.1-3.jammy_amd64.deb` |
| Ubuntu 22.04 | jammy | `aarch64` | `wkhtmltox_0.12.6.1-3.jammy_arm64.deb` |
| Debian 12 | bookworm | `x86_64` | `wkhtmltox_0.12.6.1-3.bookworm_amd64.deb` |
| Debian 12 | bookworm | `aarch64` | `wkhtmltox_0.12.6.1-3.bookworm_arm64.deb` |
| Debian 11 | bullseye | `x86_64` | `wkhtmltox_0.12.6.1-3.bullseye_amd64.deb` |
| Debian 11 | bullseye | `aarch64` | `wkhtmltox_0.12.6.1-3.bullseye_arm64.deb` |
| AlmaLinux/RHEL 9 | — | `x86_64` | `wkhtmltox-0.12.6.1-3.almalinux9.x86_64.rpm` |
| AlmaLinux/RHEL 9 | — | `aarch64` | `wkhtmltox-0.12.6.1-3.almalinux9.aarch64.rpm` |

(Full asset list: https://github.com/wkhtmltopdf/packaging/releases/tag/0.12.6.1-3)

---

## 3. Install

**Debian/Ubuntu (`.deb`)** — replace the filename with the one matched above:

```bash
wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb
sudo apt install ./wkhtmltox_0.12.6.1-3.jammy_amd64.deb
```

(`apt install ./<file>.deb` pulls in any missing dependencies automatically; plain `dpkg -i` will not.)

**AlmaLinux/RHEL (`.rpm`)**:

```bash
wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox-0.12.6.1-3.almalinux9.x86_64.rpm
sudo dnf install ./wkhtmltox-0.12.6.1-3.almalinux9.x86_64.rpm
```

---

## 4. Verify and restart

```bash
wkhtmltopdf -V
# must print: wkhtmltopdf 0.12.6 (with patched qt)

sudo supervisorctl restart all   # or however this bench's workers are managed
```

No bench/app config change is needed — Frappe finds `wkhtmltopdf` on `$PATH` automatically. The restart is just so any already-running worker processes pick up the newly-available binary.

---

## 5. Sanity check from the app

```bash
bench --site <site-name> execute core.services.pdf_service.html_to_pdf_url --kwargs "{'html': '<h1>wkhtmltopdf ok</h1>', 'file_name': 'wkhtmltopdf_check.pdf', 'is_private': 1}"
```

Should return an uploaded PDF's URL (S3 URL if S3 storage is enabled on that site, otherwise a `/private/files/...` path) instead of an `OSError: No wkhtmltopdf executable found`.
