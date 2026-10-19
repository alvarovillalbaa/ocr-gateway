export type Mode = 'auto' | 'single' | 'parallel' | 'fallback';
export type BlockKind = 'text' | 'heading' | 'table' | 'image' | 'chart' | 'diagram' | 'equation' | 'code' | 'list' | 'unknown';
export interface DocumentInput { name?: string; mimeType?: string; url?: string; dataBase64?: string; text?: string }
export interface ChunkOptions { maxCharacters?: number; overlap?: number }
export interface ParseRequest {
  document: DocumentInput; mode?: Mode; providers?: string[]; excludeProviders?: string[];
  maxProviders?: number; timeoutMs?: number; features?: ('tables' | 'images' | 'charts' | 'diagrams' | 'equations')[];
  chunking?: ChunkOptions | false; providerKeys?: Record<string,string>; providerOptions?: Record<string,Record<string,unknown>>;
  includeRaw?: boolean;
}
export interface BoundingBox { x: number; y: number; width: number; height: number; unit: 'pixel' | 'normalized' | 'point' }
export interface ProviderBlock { kind: BlockKind; text: string; bbox?: BoundingBox; confidence?: number; inferred?: boolean; imageBase64?: string; mimeType?: string; metadata?: Record<string,unknown> }
export interface ProviderPage { pageNumber?: number; text: string; blocks?: ProviderBlock[]; width?: number; height?: number }
export interface ProviderOutput { pages: ProviderPage[]; model?: string; warnings?: string[]; usage?: Record<string,unknown>; raw?: unknown }
export interface Citation { id: string; provider: string; pageNumber?: number; blockId: string; start: number; end: number; quote: string; bbox?: BoundingBox; inferred: boolean }
export interface Block extends ProviderBlock { id: string; start: number; end: number; citationId: string }
export interface Page { pageNumber?: number; text: string; blocks: Block[]; width?: number; height?: number }
export interface Chunk { id: string; text: string; start: number; end: number; blockIds: string[]; citationIds: string[]; pageNumbers: number[] }
export interface ParsedDocument { id: string; provider: string; model?: string; text: string; pages: Page[]; citations: Citation[]; chunks: Chunk[]; warnings: string[]; usage?: Record<string,unknown>; raw?: unknown }
export interface RoutingDecision { router: 'explicit' | 'custom' | 'rule' | 'jev' | 'openai-decisions' | 'heuristic'; providers: string[]; reason: string; confidence?: number }
export interface ParseResult { id: string; document: {name?:string;mimeType:string;url?:string}; primary: ParsedDocument; results: ParsedDocument[]; routing: RoutingDecision; errors: {provider:string;code:string;message:string}[]; warnings: string[]; durationMs: number }
export interface ProviderContext { apiKey?: string; signal: AbortSignal; fetch: typeof fetch; options: Record<string,unknown>; features: NonNullable<ParseRequest['features']> }
export interface ProviderAdapter { id: string; name: string; mimeTypes: string[]; features: NonNullable<ParseRequest['features']>; requiresKey: boolean; supportsUrl?: boolean; parse(document: DocumentInput, context: ProviderContext): Promise<ProviderOutput> }
export interface RoutingContext { request: ParseRequest; candidates: ProviderAdapter[] }
export interface RouterOptions {
  jevApiKey?: string; openaiApiKey?: string; confidenceThreshold?: number;
  decide?: (context: RoutingContext) => string[] | Promise<string[]>;
  rules?: {mimeTypes?:string[];features?:string[];providers:string[]}[];
}
export interface GatewayOptions { providerKeys?:Record<string,string>; enabledProviders?:string[]; providers?:ProviderAdapter[]; defaults?:Partial<Omit<ParseRequest,'document'>>; router?:RouterOptions; fetch?:typeof fetch }
export interface ParseClient { parse(request:ParseRequest, options?:{signal?:AbortSignal}):Promise<ParseResult> }
