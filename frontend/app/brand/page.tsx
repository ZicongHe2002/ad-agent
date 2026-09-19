"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  AdminMessages,
  CheckboxField,
  JsonObjectField,
  TextListField,
  parseJsonObject,
  splitLines,
  toIsoDateTime,
} from "@/components/admin-form";
import { Badge, Button, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, formatDateTime, statusTone } from "@/lib/format";

type PageResult<T> = { items: T[]; total: number; offset: number; limit: number };
type Brand = {
  id: string;
  name: string;
  description: string | null;
  default_language: string;
  status: "ACTIVE" | "PAUSED";
  created_at: string;
  updated_at: string;
};
type Product = {
  id: string;
  brand_id: string;
  name: string;
  category: string;
  material: string | null;
  price_min: string | number | null;
  price_max: string | number | null;
  approved_claims: Array<Record<string, unknown>>;
  forbidden_claims: Array<Record<string, unknown>>;
  active: boolean;
  created_at: string;
  updated_at: string;
};
type ProductClaim = {
  id: string;
  product_id: string;
  claim_text: string;
  evidence: Record<string, unknown>;
  status: "DRAFT" | "APPROVED" | "REJECTED" | "EXPIRED";
  approved_by_user_id: string | null;
  approved_at: string | null;
  expires_at: string | null;
  active: boolean;
  created_at: string;
};
type VoiceProfile = {
  id: string;
  brand_id: string;
  name: string;
  tone_attributes: string[];
  preferred_sentence_length: string;
  emoji_policy: Record<string, unknown>;
  allowed_phrases: string[];
  forbidden_phrases: string[];
  approved_examples: string[];
  version: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};

type BrandDraft = Pick<Brand, "name" | "default_language" | "status"> & { id?: string; description: string };
type ProductDraft = {
  id?: string;
  name: string;
  category: string;
  material: string;
  priceMin: string;
  priceMax: string;
  forbiddenClaims: string;
  active: boolean;
};
type VoiceDraft = {
  id?: string;
  name: string;
  toneAttributes: string;
  preferredSentenceLength: string;
  emojiPolicy: string;
  allowedPhrases: string;
  forbiddenPhrases: string;
  approvedExamples: string;
  active: boolean;
};

const emptyBrandDraft: BrandDraft = { name: "", description: "", default_language: "zh-CN", status: "ACTIVE" };
const emptyProductDraft: ProductDraft = {
  name: "",
  category: "",
  material: "",
  priceMin: "",
  priceMax: "",
  forbiddenClaims: "",
  active: true,
};
const emptyVoiceDraft: VoiceDraft = {
  name: "",
  toneAttributes: "",
  preferredSentenceLength: "SHORT",
  emojiPolicy: "{}",
  allowedPhrases: "",
  forbiddenPhrases: "",
  approvedExamples: "",
  active: true,
};

function claimRecordText(record: Record<string, unknown>): string {
  const text = record.claim_text ?? record.text ?? record.claim;
  return typeof text === "string" ? text : JSON.stringify(record);
}

export default function BrandPage() {
  const { user } = useAuth();
  const canManage = user?.role === "ADMIN" || user?.role === "BRAND_MANAGER";
  const [brands, setBrands] = useState<Brand[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [claims, setClaims] = useState<ProductClaim[]>([]);
  const [selectedBrandId, setSelectedBrandId] = useState("");
  const [selectedProductId, setSelectedProductId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [activeAction, setActiveAction] = useState<string>();
  const [brandDraft, setBrandDraft] = useState<BrandDraft>();
  const [productDraft, setProductDraft] = useState<ProductDraft>();
  const [voiceDraft, setVoiceDraft] = useState<VoiceDraft>();
  const [showClaimForm, setShowClaimForm] = useState(false);
  const [claimText, setClaimText] = useState("");
  const [claimEvidence, setClaimEvidence] = useState('{\n  "source_title": "",\n  "source_url": "",\n  "source_owner": ""\n}');
  const [claimExpiresAt, setClaimExpiresAt] = useState("");

  const selectedBrand = useMemo(
    () => brands.find((brand) => brand.id === selectedBrandId),
    [brands, selectedBrandId],
  );
  const selectedProduct = useMemo(
    () => products.find((product) => product.id === selectedProductId),
    [products, selectedProductId],
  );
  const brandVoices = useMemo(
    () => voices.filter((voice) => voice.brand_id === selectedBrandId),
    [selectedBrandId, voices],
  );

  const loadRegistry = useCallback(async () => {
    try {
      const [brandResult, voiceResult] = await Promise.all([
        api.get<PageResult<Brand>>("/brands?limit=500"),
        api.get<PageResult<VoiceProfile>>("/platform-accounts/voice-profiles?limit=500"),
      ]);
      setBrands(brandResult.items);
      setVoices(voiceResult.items);
      setError(undefined);
      setSelectedBrandId((current) =>
        brandResult.items.some((brand) => brand.id === current) ? current : brandResult.items[0]?.id ?? "",
      );
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.get<PageResult<Brand>>("/brands?limit=500"),
      api.get<PageResult<VoiceProfile>>("/platform-accounts/voice-profiles?limit=500"),
    ]).then(([brandResult, voiceResult]) => {
      if (!active) return;
      setBrands(brandResult.items); setVoices(voiceResult.items);
      setSelectedBrandId(brandResult.items[0]?.id ?? "");
    }).catch((reason: unknown) => { if (active) setError(errorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedBrandId) {
      return;
    }
    let active = true;
    void api.get<PageResult<Product>>(`/products?brand_id=${encodeURIComponent(selectedBrandId)}&limit=500`)
      .then((result) => {
        if (!active) return;
        setProducts(result.items);
        setSelectedProductId((current) =>
          result.items.some((product) => product.id === current) ? current : result.items[0]?.id ?? "",
        );
      })
      .catch((requestError: unknown) => {
        if (active) setError(errorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [selectedBrandId]);

  useEffect(() => {
    if (!selectedProductId) {
      return;
    }
    let active = true;
    void api.get<PageResult<ProductClaim>>(`/products/${selectedProductId}/claims?limit=500`)
      .then((result) => {
        if (active) setClaims(result.items);
      })
      .catch((requestError: unknown) => {
        if (active) setError(errorMessage(requestError));
      });
    return () => {
      active = false;
    };
  }, [selectedProductId]);

  const saveBrand = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!brandDraft) return;
    setActiveAction("brand-save");
    setError(undefined);
    setNotice(undefined);
    try {
      const body = {
        name: brandDraft.name.trim(),
        description: brandDraft.description.trim() || null,
        default_language: brandDraft.default_language.trim(),
        ...(brandDraft.id ? { status: brandDraft.status } : {}),
      };
      const saved = brandDraft.id
        ? await api.patch<Brand>(`/brands/${brandDraft.id}`, body)
        : await api.post<Brand>("/brands", body);
      setBrands((items) => brandDraft.id
        ? items.map((item) => item.id === saved.id ? saved : item)
        : [saved, ...items]);
      setSelectedBrandId(saved.id);
      setBrandDraft(undefined);
      setNotice(`Brand “${saved.name}” was ${brandDraft.id ? "updated" : "created"}.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const openProductEditor = (product?: Product) => {
    setProductDraft(product ? {
      id: product.id,
      name: product.name,
      category: product.category,
      material: product.material ?? "",
      priceMin: product.price_min === null ? "" : String(product.price_min),
      priceMax: product.price_max === null ? "" : String(product.price_max),
      forbiddenClaims: product.forbidden_claims.map(claimRecordText).join("\n"),
      active: product.active,
    } : { ...emptyProductDraft });
  };

  const saveProduct = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!productDraft || !selectedBrandId) return;
    const priceMin = productDraft.priceMin === "" ? null : Number(productDraft.priceMin);
    const priceMax = productDraft.priceMax === "" ? null : Number(productDraft.priceMax);
    if (priceMin !== null && priceMax !== null && priceMin > priceMax) {
      setError("Minimum price cannot exceed maximum price.");
      return;
    }
    setActiveAction("product-save");
    setError(undefined);
    setNotice(undefined);
    try {
      const fields = {
        name: productDraft.name.trim(),
        category: productDraft.category.trim(),
        material: productDraft.material.trim() || null,
        price_min: priceMin,
        price_max: priceMax,
        forbidden_claims: splitLines(productDraft.forbiddenClaims).map((text) => ({ claim_text: text })),
        ...(productDraft.id ? { active: productDraft.active } : { approved_claims: [] }),
      };
      const saved = productDraft.id
        ? await api.patch<Product>(`/products/${productDraft.id}`, fields)
        : await api.post<Product>("/products", { brand_id: selectedBrandId, ...fields });
      setProducts((items) => productDraft.id
        ? items.map((item) => item.id === saved.id ? saved : item)
        : [saved, ...items]);
      setSelectedProductId(saved.id);
      setProductDraft(undefined);
      setNotice(`Product “${saved.name}” was ${productDraft.id ? "updated" : "created"}.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const openVoiceEditor = (voice?: VoiceProfile) => {
    setVoiceDraft(voice ? {
      id: voice.id,
      name: voice.name,
      toneAttributes: voice.tone_attributes.join("\n"),
      preferredSentenceLength: voice.preferred_sentence_length,
      emojiPolicy: JSON.stringify(voice.emoji_policy, null, 2),
      allowedPhrases: voice.allowed_phrases.join("\n"),
      forbiddenPhrases: voice.forbidden_phrases.join("\n"),
      approvedExamples: voice.approved_examples.join("\n"),
      active: voice.active,
    } : { ...emptyVoiceDraft });
  };

  const saveVoice = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!voiceDraft || !selectedBrandId) return;
    setActiveAction("voice-save");
    setError(undefined);
    setNotice(undefined);
    try {
      const fields = {
        tone_attributes: splitLines(voiceDraft.toneAttributes),
        preferred_sentence_length: voiceDraft.preferredSentenceLength.trim(),
        emoji_policy: parseJsonObject(voiceDraft.emojiPolicy, "Emoji policy"),
        allowed_phrases: splitLines(voiceDraft.allowedPhrases),
        forbidden_phrases: splitLines(voiceDraft.forbiddenPhrases),
        approved_examples: splitLines(voiceDraft.approvedExamples),
        active: voiceDraft.active,
      };
      const saved = voiceDraft.id
        ? await api.patch<VoiceProfile>(`/platform-accounts/voice-profiles/${voiceDraft.id}`, fields)
        : await api.post<VoiceProfile>("/platform-accounts/voice-profiles", {
            brand_id: selectedBrandId,
            name: voiceDraft.name.trim(),
            ...fields,
          });
      setVoices((items) => [saved, ...items]);
      setVoiceDraft(undefined);
      setNotice(voiceDraft.id
        ? `Voice “${saved.name}” v${saved.version} was created. Existing accounts remain on their selected version.`
        : `Voice “${saved.name}” v${saved.version} was created.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const createClaim = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProductId) return;
    setActiveAction("claim-create");
    setError(undefined);
    setNotice(undefined);
    try {
      const evidence = parseJsonObject(claimEvidence, "Claim evidence");
      const meaningfulEvidence = Object.values(evidence).some((value) =>
        typeof value === "string" ? Boolean(value.trim()) : value !== null && value !== undefined,
      );
      if (!meaningfulEvidence) throw new Error("Claim evidence cannot be empty.");
      const created = await api.post<ProductClaim>(`/products/${selectedProductId}/claims`, {
        claim_text: claimText.trim(),
        evidence,
        expires_at: toIsoDateTime(claimExpiresAt),
      });
      setClaims((items) => [created, ...items]);
      setClaimText("");
      setClaimEvidence('{\n  "source_title": "",\n  "source_url": "",\n  "source_owner": ""\n}');
      setClaimExpiresAt("");
      setShowClaimForm(false);
      setNotice("Claim saved as DRAFT. Review its evidence before approval.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const changeClaimStatus = async (claim: ProductClaim, action: "approve" | "revoke") => {
    if (!selectedProductId) return;
    setActiveAction(`claim:${claim.id}`);
    setError(undefined);
    setNotice(undefined);
    try {
      const updated = await api.post<ProductClaim>(
        `/products/${selectedProductId}/claims/${claim.id}/${action}`,
      );
      setClaims((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Claim was ${action === "approve" ? "approved" : "revoked"}.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const approvedCount = claims.filter((claim) => claim.status === "APPROVED").length;
  const activeVoiceCount = brandVoices.filter((voice) => voice.active).length;

  return (
    <>
      <PageHeader
        eyebrow="SOURCE OF TRUTH"
        title="Brand knowledge"
        description="Maintain tenant-scoped brands, products, evidence-backed approved claims, forbidden claims, and immutable voice versions."
        actions={<div className="button-row"><Button onClick={() => { setLoading(true); void loadRegistry(); }} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button><Button variant="primary" onClick={() => setBrandDraft({ ...emptyBrandDraft })} disabled={!canManage}>New brand</Button></div>}
      />
      <AdminMessages error={error} notice={notice} />
      <div className="stats-grid">
        <StatCard label="Brands" value={String(brands.length)} detail="Visible tenant scope" />
        <StatCard label="Products" value={String(products.length)} detail={selectedBrand ? selectedBrand.name : "Select a brand"} tone="info" />
        <StatCard label="Approved claims" value={String(approvedCount)} detail={selectedProduct ? selectedProduct.name : "Select a product"} tone="success" />
        <StatCard label="Active voices" value={String(activeVoiceCount)} detail="Selected brand versions" tone={activeVoiceCount ? "success" : "warning"} />
      </div>

      {brandDraft ? (
        <Panel title={brandDraft.id ? "Edit brand" : "Create brand"} description="Brand changes are audited and apply only to the current tenant.">
          <form className="panel-body stack" onSubmit={(event) => void saveBrand(event)}>
            <div className="equal-grid">
              <div className="field"><label htmlFor="brand-name">Name</label><input id="brand-name" className="input" maxLength={120} required value={brandDraft.name} onChange={(event) => setBrandDraft({ ...brandDraft, name: event.target.value })} /></div>
              <div className="field"><label htmlFor="brand-language">Default language</label><input id="brand-language" className="input" minLength={2} maxLength={16} required value={brandDraft.default_language} onChange={(event) => setBrandDraft({ ...brandDraft, default_language: event.target.value })} /></div>
              <div className="field"><label htmlFor="brand-description">Description</label><textarea id="brand-description" className="textarea" value={brandDraft.description} onChange={(event) => setBrandDraft({ ...brandDraft, description: event.target.value })} /></div>
              {brandDraft.id ? <div className="field"><label htmlFor="brand-status">Status</label><select id="brand-status" className="select" value={brandDraft.status} onChange={(event) => setBrandDraft({ ...brandDraft, status: event.target.value as Brand["status"] })}><option value="ACTIVE">ACTIVE</option><option value="PAUSED">PAUSED</option></select></div> : null}
            </div>
            <div className="button-row"><Button type="submit" variant="primary" disabled={activeAction === "brand-save"}>{activeAction === "brand-save" ? "Saving…" : "Save brand"}</Button><Button type="button" onClick={() => setBrandDraft(undefined)}>Cancel</Button></div>
          </form>
        </Panel>
      ) : null}

      {loading && brands.length === 0 ? (
        <Panel><EmptyState title="Loading brand registry" detail="Reading brands and voice profiles from the API…" /></Panel>
      ) : brands.length === 0 ? (
        <Panel><EmptyState title="No brands yet" detail={canManage ? "Create the first brand to add products, claims, and a voice." : "No brands are visible in your tenant scope."} /></Panel>
      ) : (
        <div className="stack">
          <Panel title="Brand registry" description="Select a brand to manage its products and voice versions.">
            <div className="filter-bar">
              <select className="select" aria-label="Selected brand" value={selectedBrandId} onChange={(event) => { setSelectedBrandId(event.target.value); setProducts([]); setSelectedProductId(""); setClaims([]); setProductDraft(undefined); setVoiceDraft(undefined); setShowClaimForm(false); setLoadingDetail(true); }}>{brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name} · {brand.status}</option>)}</select>
              {selectedBrand ? <Button variant="ghost" disabled={!canManage} onClick={() => setBrandDraft({ id: selectedBrand.id, name: selectedBrand.name, description: selectedBrand.description ?? "", default_language: selectedBrand.default_language, status: selectedBrand.status })}>Edit selected brand</Button> : null}
            </div>
            {selectedBrand ? <dl className="detail-list"><div><dt>Status</dt><dd><Badge tone={statusTone(selectedBrand.status)}>{selectedBrand.status}</Badge></dd></div><div><dt>Language</dt><dd>{selectedBrand.default_language}</dd></div><div><dt>Description</dt><dd>{selectedBrand.description || "No description"}</dd></div><div><dt>Last updated</dt><dd>{formatDateTime(selectedBrand.updated_at)}</dd></div></dl> : null}
          </Panel>

          {productDraft ? (
            <Panel title={productDraft.id ? "Edit product" : "Add product"} description="Approved claims are maintained separately below so evidence and approval remain traceable.">
              <form className="panel-body stack" onSubmit={(event) => void saveProduct(event)}>
                <div className="equal-grid">
                  <div className="field"><label htmlFor="product-name">Name</label><input id="product-name" className="input" required maxLength={160} value={productDraft.name} onChange={(event) => setProductDraft({ ...productDraft, name: event.target.value })} /></div>
                  <div className="field"><label htmlFor="product-category">Category</label><input id="product-category" className="input" required maxLength={100} value={productDraft.category} onChange={(event) => setProductDraft({ ...productDraft, category: event.target.value })} /></div>
                  <div className="field"><label htmlFor="product-material">Material</label><textarea id="product-material" className="textarea" value={productDraft.material} onChange={(event) => setProductDraft({ ...productDraft, material: event.target.value })} /></div>
                  <TextListField id="product-forbidden" label="Forbidden claims" value={productDraft.forbiddenClaims} onChange={(event) => setProductDraft({ ...productDraft, forbiddenClaims: event.target.value })} placeholder="Guaranteed results\nBest on the market" />
                  <div className="field"><label htmlFor="product-price-min">Minimum price</label><input id="product-price-min" className="input" type="number" min={0} step="0.01" value={productDraft.priceMin} onChange={(event) => setProductDraft({ ...productDraft, priceMin: event.target.value })} /></div>
                  <div className="field"><label htmlFor="product-price-max">Maximum price</label><input id="product-price-max" className="input" type="number" min={0} step="0.01" value={productDraft.priceMax} onChange={(event) => setProductDraft({ ...productDraft, priceMax: event.target.value })} /></div>
                </div>
                {productDraft.id ? <CheckboxField id="product-active" label="Product active" detail="Inactive products cannot have claims approved." checked={productDraft.active} onChange={(event) => setProductDraft({ ...productDraft, active: event.target.checked })} /> : null}
                <div className="button-row"><Button type="submit" variant="primary" disabled={activeAction === "product-save"}>{activeAction === "product-save" ? "Saving…" : "Save product"}</Button><Button type="button" onClick={() => setProductDraft(undefined)}>Cancel</Button></div>
              </form>
            </Panel>
          ) : null}

          <Panel title="Products" description="Choose a product to manage its evidence-backed claim registry." actions={<Button variant="primary" disabled={!canManage || !selectedBrandId} onClick={() => openProductEditor()}>Add product</Button>}>
            {loadingDetail && products.length === 0 ? <EmptyState title="Loading products" detail="Reading products for the selected brand…" /> : products.length === 0 ? <EmptyState title="No products" detail="Add a product before creating approved claims." /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Product</th><th>Category</th><th>Price</th><th>Forbidden claims</th><th>Status</th><th>Actions</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td><span className="cell-primary">{product.name}</span><span className="cell-secondary">{product.material || "Material not specified"}</span></td><td>{product.category}</td><td>{product.price_min ?? "—"} – {product.price_max ?? "—"}</td><td>{product.forbidden_claims.length}</td><td><Badge tone={product.active ? "success" : "warning"}>{product.active ? "ACTIVE" : "INACTIVE"}</Badge></td><td><div className="button-row"><Button variant={selectedProductId === product.id ? "primary" : "ghost"} onClick={() => setSelectedProductId(product.id)}>Claims</Button><Button variant="ghost" disabled={!canManage} onClick={() => openProductEditor(product)}>Edit</Button></div></td></tr>)}</tbody></table></div>}
          </Panel>

          {selectedProduct ? (
            <Panel title={`Claims · ${selectedProduct.name}`} description="Approval is blocked unless the product is active, evidence exists, and the claim is not expired." actions={<Button variant="primary" disabled={!canManage} onClick={() => setShowClaimForm((value) => !value)}>{showClaimForm ? "Cancel" : "New claim"}</Button>}>
              {showClaimForm ? <form className="panel-body stack" onSubmit={(event) => void createClaim(event)}><div className="field"><label htmlFor="claim-text">Claim text</label><textarea id="claim-text" className="textarea" required maxLength={2000} value={claimText} onChange={(event) => setClaimText(event.target.value)} /></div><div className="equal-grid"><JsonObjectField id="claim-evidence" label="Approval evidence" value={claimEvidence} onChange={(event) => setClaimEvidence(event.target.value)} detail="Record the source title, URL, owner, and any verification notes." /><div className="field"><label htmlFor="claim-expiry">Evidence expires at</label><input id="claim-expiry" className="input" type="datetime-local" value={claimExpiresAt} onChange={(event) => setClaimExpiresAt(event.target.value)} /><small style={{ color: "var(--muted)" }}>Optional; expired claims cannot be approved.</small></div></div><Button type="submit" variant="primary" disabled={activeAction === "claim-create"}>{activeAction === "claim-create" ? "Saving…" : "Save draft claim"}</Button></form> : null}
              {claims.length === 0 ? <EmptyState title="No claims" detail="Add an evidence-backed claim, then explicitly approve it for generation." /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Claim</th><th>Evidence</th><th>Expiry</th><th>Status</th><th>Actions</th></tr></thead><tbody>{claims.map((claim) => <tr key={claim.id}><td><span className="cell-primary" style={{ whiteSpace: "normal", maxWidth: 420 }}>{claim.claim_text}</span><span className="cell-secondary">Created {formatDateTime(claim.created_at)}</span></td><td><span className="cell-primary">{Object.keys(claim.evidence).length} fields</span><span className="cell-secondary mono" style={{ whiteSpace: "normal", maxWidth: 300 }}>{JSON.stringify(claim.evidence)}</span></td><td>{formatDateTime(claim.expires_at)}</td><td><Badge tone={statusTone(claim.status)}>{claim.status}</Badge></td><td><div className="button-row"><Button variant="primary" disabled={!canManage || claim.status !== "DRAFT" || activeAction === `claim:${claim.id}`} onClick={() => void changeClaimStatus(claim, "approve")}>Approve</Button><Button variant="danger" disabled={!canManage || claim.status !== "APPROVED" || activeAction === `claim:${claim.id}`} onClick={() => void changeClaimStatus(claim, "revoke")}>Revoke</Button></div></td></tr>)}</tbody></table></div>}
            </Panel>
          ) : null}

          {voiceDraft ? (
            <Panel title={voiceDraft.id ? `Create new version · ${voiceDraft.name}` : "Create voice profile"} description={voiceDraft.id ? "Voice content is immutable. Saving creates a new version and does not silently migrate accounts." : "A voice defines brand expression, never a fictional consumer persona."}>
              <form className="panel-body stack" onSubmit={(event) => void saveVoice(event)}>
                <div className="equal-grid">
                  <div className="field"><label htmlFor="voice-name">Profile name</label><input id="voice-name" className="input" maxLength={100} required disabled={Boolean(voiceDraft.id)} value={voiceDraft.name} onChange={(event) => setVoiceDraft({ ...voiceDraft, name: event.target.value })} /></div>
                  <div className="field"><label htmlFor="voice-length">Preferred sentence length</label><select id="voice-length" className="select" value={voiceDraft.preferredSentenceLength} onChange={(event) => setVoiceDraft({ ...voiceDraft, preferredSentenceLength: event.target.value })}><option value="SHORT">SHORT</option><option value="MEDIUM">MEDIUM</option><option value="LONG">LONG</option></select></div>
                  <TextListField id="voice-tone" label="Tone attributes" value={voiceDraft.toneAttributes} onChange={(event) => setVoiceDraft({ ...voiceDraft, toneAttributes: event.target.value })} />
                  <JsonObjectField id="voice-emoji" label="Emoji policy" value={voiceDraft.emojiPolicy} onChange={(event) => setVoiceDraft({ ...voiceDraft, emojiPolicy: event.target.value })} />
                  <TextListField id="voice-allowed" label="Allowed phrases" value={voiceDraft.allowedPhrases} onChange={(event) => setVoiceDraft({ ...voiceDraft, allowedPhrases: event.target.value })} />
                  <TextListField id="voice-forbidden" label="Forbidden phrases" value={voiceDraft.forbiddenPhrases} onChange={(event) => setVoiceDraft({ ...voiceDraft, forbiddenPhrases: event.target.value })} />
                </div>
                <TextListField id="voice-examples" label="Approved examples" value={voiceDraft.approvedExamples} onChange={(event) => setVoiceDraft({ ...voiceDraft, approvedExamples: event.target.value })} detail="One approved, truthful example per line." />
                <CheckboxField id="voice-active" label="Version active" checked={voiceDraft.active} onChange={(event) => setVoiceDraft({ ...voiceDraft, active: event.target.checked })} />
                <div className="button-row"><Button type="submit" variant="primary" disabled={activeAction === "voice-save"}>{activeAction === "voice-save" ? "Saving…" : voiceDraft.id ? "Create version" : "Create voice"}</Button><Button type="button" onClick={() => setVoiceDraft(undefined)}>Cancel</Button></div>
              </form>
            </Panel>
          ) : null}

          <Panel title="Voice versions" description="Accounts bind to a specific immutable version; update the account explicitly after creating a replacement." actions={<Button variant="primary" disabled={!canManage || !selectedBrandId} onClick={() => openVoiceEditor()}>New voice</Button>}>
            {brandVoices.length === 0 ? <EmptyState title="No voice profiles" detail="Create a voice before registering a publishing account." /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Voice</th><th>Tone</th><th>Allowed / forbidden</th><th>Examples</th><th>Status</th><th /></tr></thead><tbody>{brandVoices.map((voice) => <tr key={voice.id}><td><span className="cell-primary">{voice.name} · v{voice.version}</span><span className="cell-secondary">{formatDateTime(voice.created_at)}</span></td><td>{voice.tone_attributes.join(", ") || "—"}</td><td>{voice.allowed_phrases.length} / {voice.forbidden_phrases.length}</td><td>{voice.approved_examples.length}</td><td><Badge tone={voice.active ? "success" : "warning"}>{voice.active ? "ACTIVE" : "INACTIVE"}</Badge></td><td><Button variant="ghost" disabled={!canManage} onClick={() => openVoiceEditor(voice)}>New version</Button></td></tr>)}</tbody></table></div>}
          </Panel>
        </div>
      )}
    </>
  );
}
