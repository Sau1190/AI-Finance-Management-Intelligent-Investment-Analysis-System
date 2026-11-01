import { createContext, useContext } from "react";

// Shared "what are we working on" state: the selected file, the symbol, navigation,
// the session activity list, and the one-shot "start this workflow" request (intent).
export const AppContext = createContext({
  file: null, setFile: () => {},
  symbol: "AAA", setSymbol: () => {},
  go: () => {},
  record: () => {},
  intentNonce: 0, claimIntent: () => false,
  runAction: () => {},
});
export const useApp = () => useContext(AppContext);
