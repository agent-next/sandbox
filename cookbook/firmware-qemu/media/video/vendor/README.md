# Vendored GSAP

`gsap.min.js` is GSAP **3.14.2**, byte-identical to the upstream npm
tarball, vendored so `hyperframes render` never needs the network
(the composition is rendered headless in a sandbox with no egress).

* upstream: https://www.npmjs.com/package/gsap
* tarball:  https://registry.npmjs.org/gsap/-/gsap-3.14.2.tgz
* sha256:   c174bfce53a729418d57a8ad8625e7247c793a22fef8e2851e3cfa3de9cd8280
  (matches `package/dist/gsap.min.js` inside that tarball)
* licence:  GreenSock standard licence, no charge for most use; the terms
  are printed in the file header. See https://gsap.com/standard-license

Verify:

```
curl -fsSL -o /tmp/gsap.tgz https://registry.npmjs.org/gsap/-/gsap-3.14.2.tgz
tar -xzf /tmp/gsap.tgz -C /tmp package/dist/gsap.min.js
sha256sum /tmp/package/dist/gsap.min.js gsap.min.js
```
