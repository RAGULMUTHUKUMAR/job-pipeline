# Gdrive.md — Google Drive & MCP Operational Runbook

> **Permanent project documentation.** This file is the authoritative source of truth for how this project uses Google Drive and the Google Drive MCP.
>
> **Location:** `/home/ragul/job-pipeline/Gdrive.md`
>
> **Last verified:** 2026-08-22

---

## Purpose

This document prevents a critical failure mode: **during a future Claude/agent session, the agent may forget the correct Google Drive account, use the old gdrive MCP, authenticate to the wrong Google account (Amutha Amutha), search the wrong Drive, and incorrectly conclude that resumes do not exist.**

This documentation makes that mistake extremely difficult.

---

## 1. CORRECT MCP — LOCKED

| Property            | Value                       |
| ------------------- | --------------------------- |
| **MCP Name**        | `gdrive-upload`             |
| **Transport**       | HTTP                        |
| **Endpoint**        | `http://localhost:3000/mcp` |
| **Package**         | `google-drive-mcp@1.3.0`    |
| **Startup Command** | `./start-gdrive-mcp.sh`     |

> **Rule:** The MCP **must** be connected to the Google account documented in Section 3.

---

## 2. FORBIDDEN / OLD MCP

The following are **FORBIDDEN** and must **NOT** be used in this project:

| Forbidden Name             | Reason                                                                            |
| -------------------------- | --------------------------------------------------------------------------------- |
| `gdrive`                   | Old/stale MCP configuration that previously caused Google Drive account confusion |
| `gdrive-mcp`               | Old package name (not version-pinned)                                             |
| `npx -y gdrive-mcp@latest` | Unpinned, pulls latest which may break compatibility                              |

> **Critical:** If an agent sees both `gdrive` and `gdrive-upload` in `claude mcp list`, it **must NOT guess which one to use**. It **must use only `gdrive-upload`**.

---

## 3. CORRECT GOOGLE ACCOUNT

| Property         | Value                   |
| ---------------- | ----------------------- |
| **Display Name** | `RAGUL M`               |
| **Email**        | `ragullugar4@gmail.com` |

> **This is the required Google account for this project.**

### Previously Confused Account (DO NOT USE)

| Property         | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| **Display Name** | `Amutha Amutha`                                              |
| **Status**       | Previously authenticated through old/stale MCP configuration |
| **Action**       | **Never use this account for this project**                  |

---

## 4. GOOGLE CLOUD PROJECT / OAUTH CLIENT

| Property                 | Value                                                                      |
| ------------------------ | -------------------------------------------------------------------------- |
| **Google Cloud Project** | `job-pipeline-506007`                                                      |
| **OAuth Client ID**      | `919803026892-digob6irqi5nmajt3pl5ggk7hmp84msn.apps.googleusercontent.com` |

### Credential Security (NON-NEGOTIABLE)

- The client secret exists locally in: `client_secret_919803026892-digob6irqi5nmajt3pl5ggk7hmp84msn.apps.googleusercontent.com.json`
- **NEVER write the actual client secret into Gdrive.md**
- **NEVER commit client secrets, OAuth tokens, refresh tokens, or access tokens to Git**
- Document only: project ID, OAuth client ID, credential file name/path

---

## 5. MCP STARTUP SCRIPT

| Property | Value                                |
| -------- | ------------------------------------ |
| **File** | `~/job-pipeline/start-gdrive-mcp.sh` |

### Script Contents (Reference)

```bash
#!/bin/bash

export GOOGLE_CLIENT_ID="$(python3 -c 'import json; print(json.load(open("client_secret_919803026892-digob6irqi5nmajt3pl5ggk7hmp84msn.apps.googleusercontent.com.json"))["web"]["client_id"])')"

export GOOGLE_CLIENT_SECRET="$(python3 -c 'import json; print(json.load(open("client_secret_919803026892-digob6irqi5nmajt3pl5ggk7hmp84msn.apps.googleusercontent.com.json"))["web"]["client_secret"])')"

export MCP_TRANSPORT=http
export PORT=3000

npx -y google-drive-mcp@1.3.0
```

### What the Script Does

1. Loads `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from the local Google OAuth client JSON file
2. Sets `MCP_TRANSPORT=http` and `PORT=3000`
3. Starts `google-drive-mcp@1.3.0`

### Expected Server URL

```
http://localhost:3000/mcp
```

---

## 6. PORT

| Property         | Value                       |
| ---------------- | --------------------------- |
| **Locked Port**  | `3000`                      |
| **Expected URL** | `http://localhost:3000/mcp` |

### Before Starting the Server

```bash
ss -ltnp | grep ':3000'
```

- If the port is occupied, **identify the process before killing anything**
- Do not blindly kill unrelated processes
- If an old `google-drive-mcp` process is running, stop **only that process**

---

## 7. CLAUDE MCP CONFIGURATION

### Add MCP Configuration

```bash
claude mcp add --transport http gdrive-upload http://localhost:3000/mcp
```

### Verify Configuration

```bash
claude mcp list
```

**Expected Output:**

```
gdrive-upload:
http://localhost:3000/mcp
✔ Connected
```

### Forbidden Configuration

The project **must NOT** contain:

- `gdrive` (old/forbidden configuration)

If `gdrive` exists in `claude mcp list`, it is an old/forbidden configuration and **must not be used**.

---

## 8. OAUTH AUTHENTICATION WORKFLOW

### Correct Manual Authentication Workflow

1. **Start the server:**

   ```bash
   ./start-gdrive-mcp.sh
   ```

2. **In another terminal:**

   ```bash
   cd ~/job-pipeline
   claude
   ```

3. **Inside Claude:**

   ```
   /mcp
   ```

4. **Authenticate:**
   - Select `gdrive-upload`

5. **Select Google Account:**
   - Choose `ragullugar4@gmail.com`

6. **Grant Permissions:**
   - Grant Google Drive permissions when prompted

7. **Verify:**
   ```bash
   claude mcp list
   ```
   **Expected:**
   ```
   gdrive-upload ... ✔ Connected
   ```

### OAuth `invalid_state` Error

If Google OAuth reports:

```
invalid_state
Could not decode state parameter
```

**DO NOT randomly change credentials.**

This can indicate an OAuth/MCP state-flow problem. The agent should:

- Stop and diagnose the MCP installation/server process
- **NOT** change the Google account

---

## 9. GOOGLE DRIVE PROJECT FOLDER

| Property      | Value                               |
| ------------- | ----------------------------------- |
| **Name**      | `job-pipeline`                      |
| **Folder ID** | `1_ISdkObLCJ_pRqrrtMMxKL81I2TuEvZ4` |
| **Owner**     | `RAGUL M` (`ragullugar4@gmail.com`) |

### Purpose

Pipeline-generated files are stored here:

- `phase4_application_queue.json`
- `application_queue_phase10_run_*.json`
- `application_queue_daily_run_*.json`
- `daily_run_*_decisions.json`

---

## 10. CRITICAL RESUME LOCATION

> **THIS IS EXTREMELY IMPORTANT.**

### Resume Location Rule

**Resumes are NOT required to be inside the `job-pipeline` folder.**

The project's resume documents are stored in the **user's Google Drive root**.

### Search Behavior

| Action                    | Correct Approach                                       |
| ------------------------- | ------------------------------------------------------ |
| **Searching for resumes** | Search the user's Drive/root for resume documents      |
| **DO NOT**                | Restrict search to `1_ISdkObLCJ_pRqrrtMMxKL81I2TuEvZ4` |
| **Job-pipeline folder**   | Primarily the pipeline-output location                 |
| **Resume source**         | User's Google Drive root                               |

---

## 11. VERIFIED RESUME DOCUMENTS

### Google Docs Resumes (Verified)

| #   | Name                                        | Document ID                                    |
| --- | ------------------------------------------- | ---------------------------------------------- |
| 1   | `Ragul_M_Resume_NTTData_FullStackDeveloper` | `1cnHZ9M8uXFYTl8rhQp1zDw1SlerEmmPmgMOFXmI1Y9c` |
| 2   | `Ragul_Cisco_Isovalent_Resume`              | `1lM8BNZhF0zEzdFl0TwS7qy4adUoTPWONCd96tmUGrjA` |
| 3   | `Ragul_M_Resume_FrontendDeveloper`          | `1t3Pk--LNcQwz2K7xcXmTbqVBjv49_BbmWolFqbNNZkU` |
| 4   | `Ragul_IBM_CloudFullStack_Resume`           | `1B2n_hRUwhbWX54WqkJCH2a_pRhesokMXZtTzGtTFZgQ` |
| 5   | `Ragul_IBM_AIEngineer_Resume`               | `17RhK6oaQqw2zwDhIznwtla3FK7uPR_-Ftn2B7k2v7qQ` |

### Previously Known PDF Resume

| Name                        | Status                                                                       |
| --------------------------- | ---------------------------------------------------------------------------- |
| `Ragul_M_DevOps_Resume.pdf` | Previously found, **do not invent/hard-code an ID unless verified from MCP** |

---

## 12. GOOGLE DRIVE MCP OPERATIONS

### Required Capabilities

The MCP should be used for:

| Category     | Operations                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------- |
| **READ**     | search files, list files, inspect metadata, read Google Docs, read/download supported files |
| **DOWNLOAD** | download files when required by a project phase                                             |
| **UPLOAD**   | upload pipeline-generated files when explicitly required                                    |
| **FOLDER**   | locate/create project folders when explicitly required                                      |

### Integration Rule

> **File upload/download/read operations must happen through the configured `gdrive-upload` MCP when the phase requires Google Drive interaction.**

**Do not implement a second independent Google Drive API integration unless explicitly approved.**

---

## 13. GOOGLE DOCS RESUME READING

### Resume Processing Workflow

For resume selection:

```
1. Discover Google Docs
2. Obtain the document ID
3. Read document content using Google Drive MCP's document-reading capability
4. Extract relevant resume information
5. Match against candidate job requirements
```

### Critical Assumptions

| ❌ Don't Assume            | ✅ Correct Approach                          |
| -------------------------- | -------------------------------------------- |
| Google Doc is a normal PDF | Google Docs are Google-native documents      |
| Search only `*.pdf`        | Resumes may be Google Docs — search for both |

---

## 14. PHASE 11 RESUME WORKFLOW

```
phase4_application_queue.json
        |
        v
Identify CANDIDATE jobs
        |
        v
Search Google Drive (user's Drive root)
        |
        v
Discover resume Google Docs/PDFs
        |
        v
Read resume contents
        |
        v
Match resume against job requirements
        |
        v
SELECTED / REVIEW / NO_MATCH
        |
        v
phase11_resume_selections.json
```

> **Resume discovery step must search the user's Drive and must not assume resumes are inside the job-pipeline folder.**

---

## 15. PHASE 11 SAFETY RULES

### Phase 11 MUST NOT:

- ❌ Submit applications
- ❌ Interact with LinkedIn
- ❌ Perform browser automation
- ❌ Modify resumes
- ❌ Create resumes
- ❌ Delete resumes
- ❌ Overwrite original resumes
- ❌ Modify frozen project files
- ❌ Modify scoring logic
- ❌ Modify Phase 2B frozen implementation
- ❌ Modify `phase4_application_queue.json`

### Phase 11 IS:

> **Resume discovery, reading, matching, and selection only.**

---

## 16. ACCOUNT SAFETY CHECK

### Before Any Important Drive Operation

**Verify the authenticated account:**

| Expected    | Value                   |
| ----------- | ----------------------- |
| **Account** | `RAGUL M`               |
| **Email**   | `ragullugar4@gmail.com` |

### If MCP Returns Files Owned By `Amutha Amutha`

**STOP IMMEDIATELY.**

| Action                       | Required                                      |
| ---------------------------- | --------------------------------------------- |
| Continue searching           | ❌ NO                                         |
| Conclude resumes are missing | ❌ NO                                         |
| Modify the project           | ❌ NO                                         |
| **Report**                   | ✅ `WRONG GOOGLE DRIVE ACCOUNT AUTHENTICATED` |

---

## 17. WRONG-ACCOUNT DIAGNOSTIC

### Critical Distinction

> **`claude mcp list` showing `✔ Connected` does NOT mean the correct Google account is authenticated.**

| Scenario                                  | Meaning                                   |
| ----------------------------------------- | ----------------------------------------- |
| `gdrive-upload ✔ Connected`               | MCP server is reachable/authenticated     |
| Drive searches show `Amutha Amutha` files | **Wrong Google account is authenticated** |

The MCP connection status only proves the MCP server is reachable. The **actual Drive owner/account must be verified through Drive data**.

**This distinction is critical.**

---

## 18. TROUBLESHOOTING

### A. MCP Not Running

```bash
# Check
ss -ltnp | grep ':3000'

# Start
./start-gdrive-mcp.sh
```

### B. Port Already Occupied

```bash
# Identify
ss -ltnp | grep ':3000'
ps -fp <PID>

# Only stop the google-drive-mcp process if confirmed
```

### C. MCP Needs Authentication

```bash
# Inside Claude
/mcp
# Authenticate: gdrive-upload
```

### D. Wrong Google Account

1. Stop
2. Remove the MCP configuration if necessary
3. Stop the old MCP process
4. Restart the correct server
5. Re-authenticate with `ragullugar4@gmail.com`

### E. OAuth `invalid_state`

If:

```json
{
  "error": "invalid_state",
  "error_description": "Could not decode state parameter"
}
```

**Do NOT randomly change the Google Cloud project or credentials.**

Instead:

1. Stop the current MCP server
2. Inspect the running `google-drive-mcp` process
3. Ensure only one instance is running
4. Ensure the OAuth callback belongs to the currently running server/port
5. Restart the server cleanly
6. Repeat authentication

---

## 19. CLAUDE SESSION RECOVERY

### At Start of New Claude Code Session (Google Drive Work)

```
1. Read Gdrive.md
2. Check:  claude mcp list
3. Confirm: gdrive-upload is present
4. Confirm endpoint: http://localhost:3000/mcp
5. Verify Google account through ACTUAL Drive query
6. Only then perform Drive operations
```

> **Never rely only on `✔ Connected`**

---

## 20. PROJECT INTEGRATION

### Gdrive.md Scope

This is a **project-level operational runbook**.

Any future agent working on:

- Phase 11
- Resume selection
- Application queue uploads
- Drive file reading
- Drive downloads
- Drive uploads
- Pipeline output synchronization

**MUST read Gdrive.md before using Google Drive.**

---

## 21. CREDENTIAL SECURITY

### DO NOT Put Into Gdrive.md

- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_ACCESS_TOKEN`
- Refresh tokens
- OAuth token JSON
- Private keys
- Passwords

### DO Document

- Project ID
- OAuth client ID
- Credential file name/path if necessary
- Instructions for obtaining credentials

> **Do not expose secrets in Git.**

---

## 22. CURRENT VERIFIED STATE

| Property                     | Value                                       |
| ---------------------------- | ------------------------------------------- |
| **Correct Account**          | `RAGUL M` / `ragullugar4@gmail.com`         |
| **Correct MCP**              | `gdrive-upload`                             |
| **Transport**                | HTTP                                        |
| **Endpoint**                 | `http://localhost:3000/mcp`                 |
| **Package**                  | `google-drive-mcp@1.3.0`                    |
| **Correct Project Folder**   | `job-pipeline`                              |
| **Folder ID**                | `1_ISdkObLCJ_pRqrrtMMxKL81I2TuEvZ4`         |
| **Known Resume Google Docs** | 5                                           |
| **Resume Location**          | Google Drive root (NOT job-pipeline folder) |

---

## 23. DOCUMENTATION REQUIREMENTS

This document uses:

- **Headings** for clear navigation
- **Tables** where useful for quick reference
- **Command examples** for reproducibility
- **Warnings** for critical failure points
- **Hard rules** marked with ❌/✅ and "MUST NOT"/"MUST"
- **ASCII workflow diagrams** for process visualization

### Clearly Distinguished Concepts

| Concept                  | Description                                                           |
| ------------------------ | --------------------------------------------------------------------- |
| **Google Cloud Project** | `job-pipeline-506007` — OAuth/API project                             |
| **Google Account**       | `RAGUL M` / `ragullugar4@gmail.com` — User identity                   |
| **Google Drive**         | The file storage service                                              |
| **job-pipeline Folder**  | Drive folder `1_ISdkObLCJ_pRqrrtMMxKL81I2TuEvZ4` for pipeline outputs |
| **Resume Documents**     | 5 Google Docs + 1 PDF in Drive root                                   |
| **MCP Server**           | `google-drive-mcp@1.3.0` on port 3000                                 |

---

## 24. VALIDATION AFTER WRITING

### Validation Checklist

After creating `Gdrive.md`:

1. ✅ Read the complete file
2. ✅ Verify every section (1–24) exists
3. ✅ Verify no secret/client secret value is written
4. ✅ Verify correct account: `ragullugar4@gmail.com`
5. ✅ Verify correct MCP: `gdrive-upload`
6. ✅ Verify endpoint: `http://localhost:3000/mcp`
7. ✅ Verify old `gdrive` MCP is documented as forbidden
8. ✅ Verify job-pipeline folder ID: `1_ISdkObLCJ_pRqrrtMMxKL81I2TuEvZ4`
9. ✅ Verify resumes documented as being in Drive root
10. ✅ Verify all five known Google Doc resume IDs are correct

### Git Status Check

```bash
git status --short
```

### Expected Report

- `Gdrive.md` created
- Validation result: **PASS**
- No existing tracked project files modified

---

_End of Gdrive.md_
