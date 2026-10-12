# AP Statements Third Party Notices

Statement Desk source was adapted from the AP Vendor Statements prototype at commit ad5106179be8e284e29500d3d2fb7866eb21bbc5. No vendor PDFs are included.

The deployed frontend bundles PDF.js, Tesseract.js, Tesseract.js Core, English trained data, and the Streamlit component library. Exact versions are recorded in package.json and pnpm-lock.yaml. Full licenses, notices, and licenses for dependencies included in the bridge are in frontend/vendor/licenses/.

Rebuild runtime assets with pnpm install --frozen-lockfile and pnpm build from this directory. Node is required only for development builds, not on Streamlit Cloud.
