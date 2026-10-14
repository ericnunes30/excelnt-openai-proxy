import os
import json
import base64
import sqlite3
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class DataBlob(ctypes.Structure):
    _fields_ = [
        ('cbData', wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_char))
    ]

class DpapiDecryptor:
    def decrypt(self, encrypted_bytes: bytes) -> bytes:
        in_blob = DataBlob(
            len(encrypted_bytes),
            ctypes.cast(ctypes.create_string_buffer(encrypted_bytes), ctypes.POINTER(ctypes.c_char))
        )
        out_blob = DataBlob()
        crypt32 = ctypes.windll.crypt32
        success = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not success:
            raise RuntimeError(f"Falha ao descriptografar DPAPI: {ctypes.GetLastError()}")
        result = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return result

class MasterKeyProvider:
    def __init__(self, local_state_path: str, decryptor: DpapiDecryptor):
        self._path = local_state_path
        self._decryptor = decryptor

    def get_aes_key(self) -> bytes:
        with open(self._path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        enc_b64 = data['os_crypt']['encrypted_key']
        enc_bytes = base64.b64decode(enc_b64)
        if enc_bytes.startswith(b'DPAPI'):
            enc_bytes = enc_bytes[5:]
        return self._decryptor.decrypt(enc_bytes)

class SecretDecryptor:
    def __init__(self, master_key_provider: MasterKeyProvider):
        self._provider = master_key_provider

    def decrypt(self, raw_buffer: bytes) -> str:
        if not raw_buffer.startswith(b'v10'):
            return raw_buffer.decode('utf-8', errors='ignore')
        aes_key = self._provider.get_aes_key()
        nonce = raw_buffer[3:15]
        ciphertext = raw_buffer[15:]
        cipher = AESGCM(aes_key)
        decrypted = cipher.decrypt(nonce, ciphertext, None)
        return decrypted.decode('utf-8', errors='ignore')

@dataclass
class ExtensionCredentials:
    api_key: str
    base_url: str
    model_id: str

class VSCodeStorageScanner:
    def __init__(self, db_path: str, decryptor: SecretDecryptor):
        self._db_path = db_path
        self._decryptor = decryptor

    def scan(self) -> Optional[ExtensionCredentials]:
        if not os.path.exists(self._db_path):
            return None
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM ItemTable WHERE key LIKE 'secret%excelnt%'")
        rows = cursor.fetchall()
        conn.close()

        api_key = ""
        base_url = "https://excelnt.ai/v1"
        model_id = "claude-haiku-4-5"

        for key, val_str in rows:
            try:
                obj = json.loads(val_str)
                if isinstance(obj, dict) and obj.get('type') == 'Buffer':
                    raw_bytes = bytes(obj['data'])
                    decrypted_text = self._decryptor.decrypt(raw_bytes)
                    if "sk_live_" in decrypted_text:
                        if decrypted_text.startswith("{"):
                            parsed = json.loads(decrypted_text)
                            api_configs = parsed.get("apiConfigs", {})
                            cfg = api_configs.get("default", {})
                            api_key = cfg.get("excelntApiKey", api_key)
                            model_id = cfg.get("excelntModelId", model_id)
                        else:
                            api_key = decrypted_text
            except Exception:
                continue

        if not api_key:
            return None
        return ExtensionCredentials(api_key=api_key, base_url=base_url, model_id=model_id)

def main():
    appdata = os.environ.get("APPDATA", "")
    local_state_path = os.path.join(appdata, "Code", "Local State")
    db_path = os.path.join(appdata, "Code", "User", "globalStorage", "state.vscdb")

    if not os.path.exists(local_state_path) or not os.path.exists(db_path):
        print("[ERRO] Arquivos do VS Code nao localizados no caminho padrao.")
        return

    print("==================================================")
    print("    LOCALIZADOR DE CREDENCIAIS - EXCELNT AI")
    print("==================================================")

    dpapi = DpapiDecryptor()
    master = MasterKeyProvider(local_state_path, dpapi)
    secret_dec = SecretDecryptor(master)
    scanner = VSCodeStorageScanner(db_path, secret_dec)

    creds = scanner.scan()
    if creds:
        print("\n[SUCESSO] Credenciais localizadas na extensao:")
        print(f"API Key:     {creds.api_key}")
        print(f"Base URL:    {creds.base_url}")
        print(f"Model ID:    {creds.model_id}")
        print("==================================================")
    else:
        print("\n[AVISO] Chave da extensao nao encontrada no armazenamento seguro.")
        print("Dica: Voce ja realizou login na extensao Excelnt no VS Code?")

if __name__ == '__main__':
    main()
