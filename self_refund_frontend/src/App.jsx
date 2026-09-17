import { Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ReceiptScanPage from "./pages/customer/ReceiptScanPage";
import ItemSelectionPage from "./pages/customer/ItemSelectionPage";
import WeightVerificationPage from "./pages/customer/WeightVerificationPage";
import RefundResultPage from "./pages/customer/RefundResultPage";
import EmployeeLoginPage from "./pages/employee/EmployeeLoginPage";
import EmployeeDashboardPage from "./pages/employee/EmployeeDashboardPage";
import RefundLogsPage from "./pages/employee/RefundLogsPage";
import PendingRefundsPage from "./pages/employee/PendingRefundsPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/customer/receipt" element={<ReceiptScanPage />} />
      <Route path="/customer/items" element={<ItemSelectionPage />} />
      <Route path="/customer/verify" element={<WeightVerificationPage />} />
      <Route path="/customer/result" element={<RefundResultPage />} />

      <Route path="/employee/login" element={<EmployeeLoginPage />} />
      <Route path="/employee/dashboard" element={<EmployeeDashboardPage />} />
      <Route path="/employee/logs" element={<RefundLogsPage />} />
      <Route path="/employee/pending" element={<PendingRefundsPage />} />
    </Routes>
  );
}

export default App;