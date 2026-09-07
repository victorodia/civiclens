import os
from markdown_pdf import Section, MarkdownPdf

md_content = """# Software Requirements Specification (SRS): Civic Lens

## 1. Project Overview
**Project Name:** Civic Lens
**Purpose:** A highly secure, parallel election result viewing and collation platform designed for political organizations.

---
## 2. Core Architectural Principles
*   **Zero-Trust Security:** No entity is trusted by default.
*   **Cost-Effective Infrastructure Security:** Prioritize native cloud-provider encryption over computationally expensive application-level encryption for the MVP layer.
*   **Offline-First & PWA Mode:** The system assumes NO internet connection when capturing data.
*   **Modularity:** The codebase (FastAPI & React) will be strictly modularized.

---
## 3. High-Security & Threat Mitigation Requirements

### 3.1 Network Edge & Transit Security
*   **Requirement 3.1.1 (DDoS Mitigation):** Implementation of Cloudflare Enterprise (WAF) and "Under Attack" Bot Management mode.
*   **Requirement 3.1.2 (Strict HTTPS):** Enforcement of TLS 1.3 and HSTS for all data in transit padding against Man-In-The-Middle attacks.

### 3.2 Database Isolation & Encryption at Rest
*   **Requirement 3.2.1 (VPC):** PostgreSQL database isolated in a Virtual Private Cloud (VPC) subnet with zero public internet access.
*   **Requirement 3.2.2 (Transparent Data Encryption - TDE):** Database volume physically encrypted at rest using native Managed Database Provider settings (e.g., AWS KMS) to ensure hard drive theft is useless.
*   **Requirement 3.2.3 (Image Storage Encryption):** S3 Buckets used for storing Form EC8A images will use standard SSE-S3 encryption at rest by default.
*   **Requirement 3.2.4:** Result records follow **WORM** principles. Alterations trigger immutable `Audit Logs`.
*   **Requirement 3.2.5:** Mandatory Multi-Factor Authentication (MFA) for dashboard access.

### 3.3 Advanced Agent Security Protocols
*   **Requirement 3.3.1 (Duress Password/Panic Mode):** Agents can enter a secondary PIN if coerced physically. The backend discretely flags the payload as compromised.
*   **Requirement 3.3.2 (Device Fingerprinting):** Agent accounts are strictly bound to their hardware MAC/IMEI equivalent.

---
## 4. Deep-Offline & Poor Connectivity Requirements

### 4.1 Client-Side Payload Optimization
*   **Requirement 4.1.1 (Image Compression):** Shrink captured images down to < 300KB via WASM/JS libraries before network transmission.

### 4.2 Progressive Web App (PWA) Offline Engine
*   **Requirement 4.2.1 (IndexDB Storage):** Form data streams locally into IndexedDB.
*   **Requirement 4.2.2 (Background Sync Queue):** Network requests that timeout enter a Background Sync Queue utilizing Exponential Backoff.

### 4.3 Fallback Transmission Protocols
*   **Requirement 4.3.1 (SMS Fallback):** If TCP/IP fails, the app encodes the vote data into a dense string and triggers the native SMS app.

---
## 5. System Features & Workflows

### 5.1 Field Agent Module (Frontend)
*   **Feature 5.1.1:** Authentication with short-lived JWT tokens.
*   **Feature 5.1.2:** Soft Geofencing. GPS coordinate appending without blocking uploads.

### 5.2 Situation Room Verification Module (Admin Dashboard)
*   **Feature 5.2.1:** VPN / IP-Restricted access.
*   **Feature 5.2.2 (AI & OCR Cross-Checking):** An OCR engine reads handwritten numbers from the Form EC8A image and locks discrepant data into a "High-Risk Queue".

### 5.3 Executive Collation Dashboard
*   **Feature 5.3.1:** High-performance caching layer (Redis) executing rolling sums.
*   **Feature 5.3.2:** Interactive choropleth heat-maps utilizing real-time SSE updates.
"""

pdf = MarkdownPdf()
pdf.meta["title"] = "Civic Lens Software Requirements Specification"
pdf.add_section(Section(md_content, toc=False))

pdf.save("Civic_Lens_Comprehensive_Requirements.pdf")
print("PDF saved successfully!")
