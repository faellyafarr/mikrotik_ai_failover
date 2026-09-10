import time
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import config

def train_and_evaluate():
    try:
        df = pd.read_csv(config.DATASET_PATH)
    except FileNotFoundError:
        print("[-] Dataset not found! Ensure collect_data.py has collected the data.")
        return

    label_counts = df["label"].value_counts()
    print("\n[+]  Dataset Label Distribution:")
    print(label_counts)

    if len(label_counts) < 2:
        print("[-] Warning: Your dataset has only one type of label.")
        print("[-] Ensure you record the NORMAL (0) and DEGRADED (1) conditions before training the model.")
        return

    drop_cols = ["timestamp", "interface", "label"]
    has_session = "session_id" in df.columns
    if has_session:
        drop_cols.append("session_id")

    X = df.drop(columns=drop_cols)
    y = df["label"]

    print(f"\nTotal features used: {len(X.columns)}")
    print(f"List of Features: {list(X.columns)}")

    n_sessions = df["session_id"].nunique() if has_session else 1

    if has_session and n_sessions > 1:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
        train_idx, test_idx = next(splitter.split(X, y, groups=df["session_id"]))
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    print("\n--- Confusion Matrix ---")
    print(confusion_matrix(y_test, y_pred))

    print("\n--- Classification Report ---")
    print(classification_report(y_test, y_pred, target_names=["NORMAL (0)", "DEGRADED (1)"]))

    joblib.dump(model, config.MODEL_PATH)
    joblib.dump(list(X.columns), config.FEATURES_PATH)

    print(f"\nDONE!")


if __name__ == "__main__":
    train_and_evaluate()
