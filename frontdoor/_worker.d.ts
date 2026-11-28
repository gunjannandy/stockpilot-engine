export const DEFAULT_APP_ORIGIN: string;
export function appUrl(request: Request, appOrigin?: string): URL;
export function passOn(
  request: Request,
  env?: { APP_ORIGIN?: string },
  fetcher?: typeof fetch,
): Promise<Response>;
declare const door: { fetch(request: Request, env?: { APP_ORIGIN?: string }): Promise<Response> };
export default door;
