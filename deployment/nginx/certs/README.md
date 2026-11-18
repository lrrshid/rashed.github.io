# The HTTPS certificate (from IT)

Put two files in this folder on the VM. They are never committed and never part of the bundle.

| File | What it is |
|---|---|
| `server.crt` | The certificate for the app's DNS name (e.g. `cpc.company.local`), **followed by the intermediate chain**, PEM |
| `server.key` | Its private key, PEM, **without a password**. `chmod 600 server.key` |

The name in the certificate must match `https://<name>` that users open, or the browser warns.
After replacing them: `bash ./scripts/app.sh restart`.

Check before installing:

```bash
openssl x509 -in server.crt -noout -subject -ext subjectAltName -enddate
openssl x509 -in server.crt -noout -pubkey | sha256sum; openssl pkey -in server.key -pubout | sha256sum   # must match
```
