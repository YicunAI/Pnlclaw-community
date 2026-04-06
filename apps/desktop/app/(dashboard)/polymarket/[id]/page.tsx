import PolymarketEventPage from "./client-page"

export function generateStaticParams() {
  return [{ id: "placeholder" }];
}

export default function Page() {
  return <PolymarketEventPage />;
}
