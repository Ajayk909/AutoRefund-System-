# AutoRefund kiosk UI

React 19 + Vite frontend for AutoRefund. See the [main README](../README.md) for setup.

```bat
npm ci
npm run dev       REM http://127.0.0.1:5173 with hot reload
npm run build     REM production build in dist\
npm run preview   REM serve dist\ on http://127.0.0.1:5173
```

- Backend URL: `src/services/api.js` (override with `VITE_API_ORIGIN` in `.env.local`)
- USB barcode scanner (HID keyboard) support: `src/hooks/useBarcodeScanner.js`
