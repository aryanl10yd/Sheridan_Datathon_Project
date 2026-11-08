import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score, roc_curve

def generate_sentinel_dataset(n_samples=2500, random_state=42):
    """
    Generates telemetry & vulnerability exploit dataset.
    Simulates CVEs, CISA KEV exploitation, public PoCs, and Ground Station targets.
    """
    np.random.seed(random_state)
    cve_ids = [f"CVE-2026-{1000 + i}" for i in range(n_samples)]
    
    cvss_base = np.round(np.random.beta(5, 2, n_samples) * 10, 1)
    epss_score = np.clip(np.random.exponential(scale=0.08, size=n_samples), 0.001, 0.98)
    
    has_public_poc = np.random.binomial(1, p=0.22, size=n_samples)
    mentions_rce = np.random.binomial(1, p=0.30, size=n_samples)
    mentions_memory_corruption = np.random.binomial(1, p=0.18, size=n_samples)
    mentions_auth_bypass = np.random.binomial(1, p=0.15, size=n_samples)
    
    targets_ground_station = np.random.binomial(1, p=0.12, size=n_samples)
    downlink_scada_impact = np.where(targets_ground_station == 1, np.random.binomial(1, p=0.65, size=n_samples), 0)
    
    days_since_disclosure = np.random.randint(1, 45, size=n_samples)
    github_exploit_chatter = np.random.poisson(lam=(has_public_poc * 12 + 1), size=n_samples)
    
    # Weaponization formula: PoC + RCE + Threat Chatter drives actual weaponization, not CVSS alone
    logit = (
        -4.2
        + 0.15 * cvss_base
        + 3.2 * epss_score
        + 2.8 * has_public_poc
        + 1.9 * mentions_rce
        + 1.4 * mentions_memory_corruption
        + 1.6 * targets_ground_station
        + 0.12 * github_exploit_chatter
    )
    prob_weaponized = 1 / (1 + np.exp(-logit))
    is_weaponized = np.random.binomial(1, prob_weaponized)
    
    return pd.DataFrame({
        'cve_id': cve_ids,
        'cvss_score': cvss_base,
        'epss_score': epss_score,
        'has_public_poc': has_public_poc,
        'mentions_rce': mentions_rce,
        'mentions_memory_corruption': mentions_memory_corruption,
        'mentions_auth_bypass': mentions_auth_bypass,
        'targets_ground_station': targets_ground_station,
        'downlink_scada_impact': downlink_scada_impact,
        'days_since_disclosure': days_since_disclosure,
        'github_exploit_chatter': github_exploit_chatter,
        'is_weaponized': is_weaponized
    })

def train_sentinel_model(df):
    feature_cols = [
        'cvss_score',
        'epss_score',
        'has_public_poc',
        'mentions_rce',
        'mentions_memory_corruption',
        'mentions_auth_bypass',
        'targets_ground_station',
        'downlink_scada_impact',
        'days_since_disclosure',
        'github_exploit_chatter'
    ]
    
    X = df[feature_cols]
    y = df['is_weaponized']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)
    
    model = RandomForestClassifier(n_estimators=120, max_depth=8, random_state=42)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    roc_auc = roc_auc_score(y_test, y_prob)
    report = classification_report(y_test, y_pred, target_names=['Theoretical Flaw', 'Weaponized Exploit'])
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    
    return model, feature_cols, X_test, y_test, y_prob, roc_auc, report, importances

def evaluate_and_plot(y_test, y_prob, importances, output_dir="./output"):
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Feature Importance Plot
    plt.figure(figsize=(9, 5))
    colors = ['#d62728' if 'ground' in idx or 'downlink' in idx else '#1f77b4' for idx in importances.index]
    importances.sort_values().plot(kind='barh', color=colors)
    plt.title("Sentinel ML: Key Drivers of Real-World Weaponization", fontsize=12, fontweight='bold')
    plt.xlabel("Random Forest Feature Importance")
    plt.tight_layout()
    feat_path = os.path.join(output_dir, "feature_importance.png")
    plt.savefig(feat_path, dpi=200)
    plt.close()
    
    # 2. ROC Curve Plot
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    plt.figure(figsize=(7, 5))
    plt.plot(fpr, tpr, color='#0052cc', lw=2.5, label=f'Sentinel ROC (AUC = {roc_auc_score(y_test, y_prob):.3f})')
    plt.plot([0, 1], [0, 1], color='gray', linestyle='--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('Sentinel Exploit Momentum ROC Curve', fontsize=12, fontweight='bold')
    plt.legend(loc="lower right")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    roc_path = os.path.join(output_dir, "roc_curve.png")
    plt.savefig(roc_path, dpi=200)
    plt.close()
    
    return feat_path, roc_path

def simulate_flight_interlock(model, feature_cols):
    """
    Simulates triage on an unanalyzed 2026 zero-day attacking satellite ground telemetry.
    """
    sample_threat = pd.DataFrame([{
        'cvss_score': 7.2,
        'epss_score': 0.78,
        'has_public_poc': 1,
        'mentions_rce': 1,
        'mentions_memory_corruption': 1,
        'mentions_auth_bypass': 0,
        'targets_ground_station': 1,
        'downlink_scada_impact': 1,
        'days_since_disclosure': 2,
        'github_exploit_chatter': 28
    }])[feature_cols]
    
    momentum_prob = float(model.predict_proba(sample_threat)[0, 1])
    is_critical = bool(momentum_prob > 0.70)
    
    return {
        "cve": "CVE-2026-9481 (CCSDS Telemetry Buffer Overflow)",
        "exploit_momentum_score": f"{momentum_prob * 100:.1f}%",
        "nist_status": "UNANALYZED / PENDING",
        "target_infrastructure": "Ground Station Downlink Telemetry Parser",
        "two_man_rule_triggered": is_critical,
        "interlock_status": "LOCKED - Physical Key Turn Required on Flight Console" if is_critical else "CLEARED"
    }

if __name__ == "__main__":
    print("=== SENTINEL MACHINE LEARNING PIPELINE ===")
    print("Ingesting vulnerability data...")
    df = generate_sentinel_dataset()
    print(f"Loaded {df.shape[0]} vulnerabilities.")
    
    print("\nTraining Exploit Momentum Classifier...")
    model, features, X_test, y_test, y_prob, auc, report, importances = train_sentinel_model(df)
    
    print(f"\n[+] Model ROC-AUC Score: {auc:.4f}")
    print("\n[+] Classification Report:\n" + report)
    
    feat_img, roc_img = evaluate_and_plot(y_test, y_prob, importances)
    print(f"[+] Saved evaluation plots to ./output/")
    
    print("\n=== MISSION CONTROL FLIGHT INTERLOCK SIMULATION ===")
    alert = simulate_flight_interlock(model, features)
    print(json.dumps(alert, indent=2))
