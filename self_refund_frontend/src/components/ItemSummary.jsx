import { BoxIcon } from "./Icons";

// Grey tile with a box icon where a product photo would go.
export function ItemThumb({ size }) {
  return (
    <div className="k-thumb" style={{ width: size, height: size }}>
      <BoxIcon size={Math.round(size * 0.42)} stroke={1.5} />
    </div>
  );
}

// Item photo, name and receipt number: the top of the kiosk summary cards.
export function ItemSummary({ name, receiptNumber }) {
  return (
    <div className="k-item-summary">
      <ItemThumb size={88} />
      <div>
        <div className="k-item-summary-name">{name}</div>
        <div className="k-item-summary-receipt">Receipt {receiptNumber}</div>
      </div>
    </div>
  );
}
