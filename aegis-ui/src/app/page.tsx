import Link from "next/link";
import { Shield, Zap, Search, TrendingUp, BarChart3, Users, ArrowRight, Check } from "lucide-react";

const features = [
  { icon: Zap, title: "Anomaly Detection", desc: "Deterministic CUSUM and bias analysis detects structural shifts, not noise." },
  { icon: Search, title: "Root Cause Analysis", desc: "Automated causal reasoning traces every signal to its origin." },
  { icon: TrendingUp, title: "Strategic Recommendations", desc: "Action-ready decisions with confidence scoring and evidence chains." },
  { icon: BarChart3, title: "Segment Intelligence", desc: "Cross-segment analysis isolates performance drivers by product, region, and channel." },
  { icon: Users, title: "Executive Briefings", desc: "AI-narrated intelligence briefings grounded in deterministic analysis." },
  { icon: Shield, title: "Decision Governance", desc: "Every recommendation carries audit trails, confidence bounds, and evidence." },
];

const tiers = [
  { name: "Starter", price: "$499", period: "/mo", features: ["5 metrics", "CSV upload", "1 user", "Monthly reports", "Email support"], cta: "Start Free Trial" },
  { name: "Pro", price: "$1,499", period: "/mo", features: ["25 metrics", "All integrations", "5 users", "AEGIS Analyst chat", "Weekly reports", "Priority support"], cta: "Start Free Trial", popular: true },
  { name: "Enterprise", price: "Custom", period: "", features: ["Unlimited metrics", "SSO + RBAC", "Unlimited users", "Custom integrations", "SLA guarantee", "Dedicated success manager"], cta: "Contact Sales" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#020409] text-[#F8FAFC] overflow-y-auto">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 border-b border-[#2A2F3A]/50 backdrop-blur-xl bg-[#020409]/80">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-6 h-6 text-[#A855F7]" />
            <span className="font-bold tracking-[0.2em] text-sm">AEGIS</span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm text-[#94A3B8]">
            <a href="#features" className="hover:text-[#F8FAFC] transition-colors">Platform</a>
            <a href="#pricing" className="hover:text-[#F8FAFC] transition-colors">Pricing</a>
            <a href="#" className="hover:text-[#F8FAFC] transition-colors">Documentation</a>
            <Link href="/dashboard" className="px-4 py-2 bg-[#A855F7] text-white text-sm font-medium rounded hover:bg-[#9333EA] transition-colors">
              Launch Dashboard
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div>
            <div className="inline-flex items-center px-3 py-1 text-[11px] font-mono border border-[#A855F7]/30 text-[#A855F7] bg-[#A855F7]/5 rounded-full mb-6">
              DECISION INTELLIGENCE INFRASTRUCTURE
            </div>
            <h1 className="text-5xl lg:text-6xl font-bold leading-[1.1] mb-6">
              Don&apos;t read charts.
              <br />
              <span className="text-[#A855F7]">Make decisions.</span>
            </h1>
            <p className="text-lg text-[#94A3B8] leading-relaxed mb-8 max-w-lg">
              AEGIS transforms fragmented business data into deterministic decisions with confidence scoring, root cause analysis, and executive-grade intelligence briefings.
            </p>
            <div className="flex items-center gap-4">
              <Link href="/dashboard" className="inline-flex items-center gap-2 px-6 py-3 bg-[#A855F7] text-white font-medium rounded hover:bg-[#9333EA] transition-all hover:shadow-[0_0_30px_rgba(168,85,247,0.3)]">
                Request Access <ArrowRight className="w-4 h-4" />
              </Link>
              <a href="#features" className="inline-flex items-center gap-2 px-6 py-3 border border-[#2A2F3A] text-[#94A3B8] rounded hover:border-[#3A4150] hover:text-[#F8FAFC] transition-colors">
                See Platform
              </a>
            </div>
          </div>

          {/* Dashboard Preview */}
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-r from-[#A855F7]/10 to-transparent rounded-xl blur-3xl" />
            <div className="relative bg-[#0E111A] border border-[#2A2F3A] rounded-xl p-6 shadow-2xl">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                <div className="w-2 h-2 rounded-full bg-amber-500" />
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="ml-2 text-[10px] font-mono text-[#64748B]">AEGIS Command Center</span>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 text-[9px] font-mono text-emerald-400 border border-emerald-500/30 bg-emerald-500/10 rounded">ACTIONABLE</span>
                  <span className="text-[10px] font-mono text-[#64748B]">Confidence: 82%</span>
                </div>
                <p className="text-sm text-[#F8FAFC]">Cost Efficiency Improving Across Tier 1 Channels</p>
                <div className="grid grid-cols-3 gap-2">
                  {[{ m: "Revenue", v: "$4.2M", d: "+5.3%" }, { m: "Cost", v: "$1.1M", d: "-12.5%" }, { m: "Conv.", v: "3.2%", d: "+0.4%" }].map((k) => (
                    <div key={k.m} className="bg-[#05070D] rounded p-2.5 border border-[#2A2F3A]">
                      <div className="text-[9px] text-[#64748B] uppercase">{k.m}</div>
                      <div className="text-sm font-mono text-[#F8FAFC]">{k.v}</div>
                      <div className="text-[10px] font-mono text-emerald-400">{k.d}</div>
                    </div>
                  ))}
                </div>
                <div className="h-16 bg-[#05070D] rounded border border-[#2A2F3A] flex items-end p-2 gap-[2px]">
                  {Array.from({ length: 30 }).map((_, i) => (
                    <div key={i} className="flex-1 bg-[#A855F7]/30 rounded-t" style={{ height: `${20 + Math.sin(i * 0.4) * 15 + Math.random() * 10}px` }} />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="py-12 border-y border-[#2A2F3A]/50">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <p className="text-[11px] font-mono uppercase tracking-[0.1em] text-[#64748B] mb-6">Trusted by data-driven enterprises</p>
          <div className="flex items-center justify-center gap-12 text-[#334155]">
            {["Enterprise Co.", "DataCorp", "Insight Labs", "Scale AI", "NexGen"].map((n) => (
              <span key={n} className="text-sm font-medium tracking-wide">{n}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold mb-4">Signal → Decision → Action</h2>
            <p className="text-[#94A3B8] max-w-2xl mx-auto">Every competitor stops at &ldquo;signal.&rdquo; AEGIS completes the chain with deterministic confidence scoring and evidence-backed recommendations.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="card p-6 hover:border-[#A855F7]/30 transition-all group">
                <div className="w-10 h-10 rounded bg-[#A855F7]/10 flex items-center justify-center mb-4 group-hover:bg-[#A855F7]/20 transition-colors">
                  <Icon className="w-5 h-5 text-[#A855F7]" />
                </div>
                <h3 className="text-base font-semibold mb-2">{title}</h3>
                <p className="text-sm text-[#64748B] leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 px-6 bg-[#05070D]/50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold mb-4">Enterprise Intelligence, SaaS Pricing</h2>
            <p className="text-[#94A3B8]">Start with decisions in minutes. Scale to enterprise.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {tiers.map((tier) => (
              <div key={tier.name} className={`card p-6 flex flex-col ${tier.popular ? "border-[#A855F7]/50 shadow-[0_0_30px_rgba(168,85,247,0.1)] relative" : ""}`}>
                {tier.popular && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 text-[10px] font-mono bg-[#A855F7] text-white rounded-full">MOST POPULAR</span>
                )}
                <h3 className="text-lg font-semibold mb-1">{tier.name}</h3>
                <div className="flex items-baseline gap-1 mb-6">
                  <span className="text-3xl font-bold font-mono">{tier.price}</span>
                  <span className="text-sm text-[#64748B]">{tier.period}</span>
                </div>
                <ul className="space-y-3 mb-8 flex-1">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-[#94A3B8]">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" /> {f}
                    </li>
                  ))}
                </ul>
                <button className={`w-full py-2.5 rounded text-sm font-medium transition-colors ${tier.popular ? "bg-[#A855F7] text-white hover:bg-[#9333EA]" : "border border-[#2A2F3A] text-[#94A3B8] hover:border-[#3A4150] hover:text-[#F8FAFC]"}`}>
                  {tier.cta}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-4">Start making decisions that matter.</h2>
          <p className="text-[#94A3B8] mb-8">Upload your first dataset. Get your first insight in under 3 minutes.</p>
          <Link href="/dashboard" className="inline-flex items-center gap-2 px-8 py-3 bg-[#A855F7] text-white font-medium rounded-lg hover:bg-[#9333EA] transition-all hover:shadow-[0_0_40px_rgba(168,85,247,0.3)] text-lg">
            Get Started <ArrowRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#2A2F3A] py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-[11px] text-[#64748B]">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-[#A855F7]" />
            <span className="font-mono">AEGIS Decision Intelligence</span>
          </div>
          <div className="flex items-center gap-6 font-mono">
            <span>SOC 2 Compliant</span>
            <span>Enterprise Ready</span>
            <span>99.9% Uptime</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
