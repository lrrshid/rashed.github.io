# The HTTPS certificate (from IT)

Without these two files `install.sh` makes a **self-signed** certificate, so the site works at once but browsers warn
about it. To use IT's certificate, put two files here (in the kit's `certs/` folder before running `install.sh`, or in
`/opt/cpc/certs/` afterwards). They are never committed and never part of the kit.

| File | What it is |
|---|---|
| `server.crt` | The certificate for the name users open (e.g. `cpc.company.local`), **followed by the intermediate chain**, PEM |
| `server.key` | Its private key, PEM, **without a password** |

The name in the certificate must match `https://<name>` that users open, or the browser warns.

Replacing the self-signed one later:

```bash
cp server.crt server.key /opt/cpc/certs/
rm -f /opt/cpc/certs/SELF-SIGNED
sudo /opt/cpc/install.sh            # checks the pair and reloads nginx (settings and data are kept)
```

Check a pair before installing:

```bash
openssl x509 -in server.crt -noout -subject -ext subjectAltName -enddate
openssl x509 -in server.crt -noout -pubkey | sha256sum; openssl pkey -in server.key -pubout | sha256sum   # must match
```
