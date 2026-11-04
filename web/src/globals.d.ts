/// <reference types="vite/client" />

declare const __APP_VERSION__: string;
declare const __APP_BUILD__: string;

declare module "virtual:pwa-register" {
  export interface RegisterSWOptions {
    immediate?: boolean;
    onNeedRefresh?: () => void;
    onRegisteredSW?: (url: string, registration: ServiceWorkerRegistration | undefined) => void;
    onRegisterError?: (error: unknown) => void;
  }
  export function registerSW(options?: RegisterSWOptions): (reloadPage?: boolean) => Promise<void>;
}

/**
 * What the macOS menu bar can ask the interface to open: a Settings page by name — "settings" alone
 * is General — or one of the vocabulary's own operations, which open Settings ▸ Data.
 */
type AcervoCommand = "export" | "import" | "delete" | "settings" | `settings:${string}`;

interface Window {
  acervo?: {
    command(name: AcervoCommand): void;
    /** The application's own settings changed: a download moved on, a build arrived. */
    hostState(state: import("./host").HostState): void;
  };
  webkit?: {
    messageHandlers?: {
      acervo?: { postMessage(message: unknown): Promise<unknown> };
    };
  };
}
