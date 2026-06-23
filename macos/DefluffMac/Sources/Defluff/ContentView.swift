import SwiftUI

// MARK: - Vintage theme

/// Palette and type ramp inspired by the app icon: warm cream paper,
/// black ink, sepia accents, and a refined New York serif throughout.
private enum Theme {
    static let paper = Color(red: 0.09, green: 0.08, blue: 0.07)
    static let paperRaised = Color(red: 0.14, green: 0.125, blue: 0.105)
    static let ink = Color(red: 0.93, green: 0.89, blue: 0.81)
    static let inkSoft = Color(red: 0.70, green: 0.66, blue: 0.58)
    static let inkFaint = Color(red: 0.48, green: 0.44, blue: 0.38)
    static let hairline = Color(red: 0.27, green: 0.24, blue: 0.20)
    static let accent = Color(red: 0.82, green: 0.64, blue: 0.34)

    /// Wordmark / display headings — Apple's "New York" serif, the refined
    /// editorial face that anchors the brand.
    static func display(_ size: CGFloat, weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }

    /// Reading face — New York serif — for summaries, highlights and body copy.
    static func serif(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }

    /// True italic of the reading face, used for asides and pull quotes.
    static func serifItalic(_ size: CGFloat) -> Font {
        .system(size: size, design: .serif).italic()
    }

    /// UI chrome — SF Pro — for labels, buttons, badges and status text.
    static func text(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }

    static func mono(_ size: CGFloat) -> Font {
        .system(size: size, design: .monospaced)
    }
}

private extension View {
    /// A raised "card" of paper with a hairline rule, used for panels.
    func vintageCard(padding: CGFloat = 22) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.paperRaised)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(Theme.hairline, lineWidth: 1)
            )
    }
}

private struct VintageButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.text(15, weight: .semibold))
            .tracking(0.5)
            .foregroundStyle(Theme.paper)
            .padding(.horizontal, 22)
            .padding(.vertical, 13)
            .background(Theme.ink.opacity(configuration.isPressed ? 0.82 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 9))
    }
}

private struct VintageFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(Theme.text(16))
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 16)
            .padding(.vertical, 13)
            .background(Theme.paperRaised)
            .clipShape(RoundedRectangle(cornerRadius: 9))
            .overlay(
                RoundedRectangle(cornerRadius: 9)
                    .strokeBorder(Theme.hairline, lineWidth: 1)
            )
    }
}

struct ContentView: View {
    @State private var urlText = ""
    @State private var isSubmitting = false
    @State private var statusMessage = ""
    @State private var consumeResponse: ConsumeResponse?
    @State private var liveAgentTraces: [AgentTrace] = []
    @State private var agentLogExpanded = true
    @State private var streamedContent: ContentResponse?
    @State private var streamedAnalysis: ConsumptionAnalysis?
    @State private var streamedHighlights: [Highlight] = []
    @State private var streamedChapters: [Chapter] = []
    @State private var learnedKeys: Set<String> = []

    @State private var discussion: [DiscussTurn] = []
    @State private var questionText = ""
    @State private var isDiscussing = false

    let client: BackendClient

    var body: some View {
        ZStack {
            WindowFullScreenSizer()
            Theme.paper.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar

                mainContent
                    .padding(.horizontal, 44)
                    .padding(.top, 30)
                    .padding(.bottom, 24)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)

                if showAgentDrawer {
                    agentLogDrawer(currentAgents)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
        }
        .tint(Theme.accent)
        .preferredColorScheme(.dark)
        .frame(minWidth: 900, minHeight: 600)
        .animation(.easeInOut(duration: 0.25), value: showAgentDrawer)
    }

    /// Whichever set of traces is current: the finished response's, or the
    /// ones streaming in live.
    private var currentAgents: [AgentTrace] {
        consumeResponse?.agentTraces ?? liveAgentTraces
    }

    /// The bottom drawer only earns its space once there's something to show.
    private var showAgentDrawer: Bool {
        isSubmitting || !currentAgents.isEmpty
    }

    // MARK: Top bar (brand)

    private var topBar: some View {
        HStack(spacing: 13) {
            logoMark
            Text("Defluff")
                .font(Theme.display(30))
                .foregroundStyle(Theme.ink)
                .tracking(0.5)
            Spacer()
        }
        .padding(.horizontal, 44)
        .padding(.vertical, 16)
        .background(Theme.paper)
    }

    @ViewBuilder
    private var logoMark: some View {
        if let logo = Self.logoImage {
            logo
                .resizable()
                .interpolation(.high)
                .scaledToFit()
                .frame(width: 38, height: 38)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
    }

    /// The app icon, loaded from the bundled Resources (copied in by the build
    /// script). Falls back to nil — a text-only wordmark — when the asset isn't
    /// present, e.g. in SwiftUI previews.
    private static let logoImage: Image? = {
        guard let url = Bundle.main.url(forResource: "DefluffIcon-light", withExtension: "png"),
              let nsImage = NSImage(contentsOf: url) else {
            return nil
        }
        return Image(nsImage: nsImage)
    }()

    // MARK: Main content

    private var mainContent: some View {
        VStack(spacing: 22) {
            formArea
            resultsArea
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .animation(.easeInOut(duration: 0.3), value: consumeResponse != nil)
    }

    private var formArea: some View {
        VStack(spacing: 12) {
            form
        }
        .frame(maxWidth: 640)
        .frame(maxWidth: .infinity)
    }

    private var form: some View {
        HStack(spacing: 12) {
            TextField("Paste a YouTube or article link", text: $urlText)
                .textFieldStyle(VintageFieldStyle())
                .onSubmit { Task { await submit() } }

            Button {
                Task { await submit() }
            } label: {
                if isSubmitting {
                    ProgressView()
                        .controlSize(.small)
                        .tint(Theme.paper)
                } else {
                    Text("Analyze")
                }
            }
            .buttonStyle(VintageButtonStyle())
            .disabled(isSubmitting || !canSubmit)
            .opacity((isSubmitting || !canSubmit) ? 0.45 : 1)
            .animation(.easeInOut(duration: 0.2), value: isSubmitting)
            .animation(.easeInOut(duration: 0.2), value: canSubmit)
        }
    }

    // MARK: Results

    /// The reading surface. The agent log no longer lives here — it sits in the
    /// bottom drawer — so this area is just the distilled digest (final or live).
    @ViewBuilder
    private var resultsArea: some View {
        if let consumeResponse {
            ScrollView {
                consumeBody(consumeResponse)
                    .vintageCard(padding: 26)
                    .frame(maxWidth: 920)
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 4)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .transition(.opacity)
        } else if hasStreamedDigest {
            ScrollView {
                liveDigestPanel()
                    .vintageCard(padding: 26)
                    .frame(maxWidth: 920)
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 4)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .transition(.opacity)
        } else if isSubmitting {
            workingPlaceholder
        } else if !statusMessage.isEmpty {
            Text(statusMessage)
                .font(Theme.serif(15))
                .foregroundStyle(Theme.inkSoft)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                .transition(.opacity)
        } else {
            Spacer(minLength: 0)
        }
    }

    /// Shown while the agents are working but nothing has streamed back yet;
    /// the live progress itself is in the bottom drawer.
    private var workingPlaceholder: some View {
        VStack(spacing: 14) {
            ProgressView()
                .controlSize(.large)
                .tint(Theme.inkSoft)
            Text(statusMessage.isEmpty ? "Distilling…" : statusMessage)
                .font(Theme.serif(15))
                .foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
    }

    private var hasStreamedDigest: Bool {
        streamedContent != nil
            || streamedAnalysis != nil
            || !streamedHighlights.isEmpty
            || !streamedChapters.isEmpty
    }

    // MARK: Agent log (bottom drawer)

    /// A VSCode-terminal-style panel pinned to the bottom: a slim, always-tappable
    /// header that toggles a fixed-height scrollable list of agent traces. It auto-
    /// expands while working and collapses once the digest is ready (see submit()).
    @ViewBuilder
    private func agentLogDrawer(_ agents: [AgentTrace]) -> some View {
        VStack(spacing: 0) {
            Rectangle().fill(Theme.hairline).frame(height: 1)

            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    agentLogExpanded.toggle()
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "terminal")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Theme.inkFaint)

                    Text("AGENT LOG")
                        .font(Theme.text(11, weight: .semibold))
                        .tracking(2)
                        .foregroundStyle(Theme.inkSoft)

                    Text("\(agents.count)")
                        .font(Theme.text(11, weight: .semibold))
                        .foregroundStyle(Theme.inkFaint)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 1)
                        .background(Theme.paper)
                        .clipShape(Capsule())

                    if isSubmitting {
                        workingIndicator
                    }

                    Spacer()

                    Image(systemName: "chevron.up")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Theme.inkFaint)
                        .rotationEffect(.degrees(agentLogExpanded ? 180 : 0))
                }
                .padding(.horizontal, 44)
                .padding(.vertical, 9)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if agentLogExpanded {
                Rectangle().fill(Theme.hairline).frame(height: 1)

                ScrollView {
                    VStack(spacing: 0) {
                        agentRows(agents)
                    }
                    .padding(.horizontal, 44)
                    .padding(.vertical, 4)
                }
                .frame(height: 220)
            }
        }
        .background(Theme.paperRaised)
    }

    private func agentRows(_ agents: [AgentTrace]) -> some View {
        ForEach(Array(agents.enumerated()), id: \.element.id) { index, agent in
            VStack(spacing: 0) {
                if index > 0 {
                    Divider().overlay(Theme.hairline.opacity(0.6))
                }
                agentRow(agent)
            }
            .transition(.asymmetric(
                insertion: .move(edge: .leading).combined(with: .opacity),
                removal: .opacity
            ))
        }
    }

    private func agentRow(_ agent: AgentTrace) -> some View {
        HStack(alignment: .top, spacing: 14) {
            statusGlyph(agent.status)
                .padding(.top, 5)

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    Text(agent.name)
                        .font(Theme.serif(18, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(agent.status.uppercased())
                        .font(Theme.text(10, weight: .semibold))
                        .tracking(1.5)
                        .foregroundStyle(agentStatusColor(agent.status))
                }

                Text(agent.summary)
                    .font(Theme.serif(14))
                    .foregroundStyle(Theme.inkSoft)
                    .textSelection(.enabled)

                ForEach(agent.details, id: \.self) { detail in
                    HStack(alignment: .top, spacing: 8) {
                        Text("—")
                            .foregroundStyle(Theme.inkFaint)
                        Text(detail)
                            .font(Theme.serif(13))
                            .foregroundStyle(Theme.inkSoft)
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workingIndicator: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
                .tint(Theme.inkSoft)
            Text("working")
                .font(Theme.serifItalic(13))
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func statusGlyph(_ status: String) -> some View {
        Circle()
            .fill(agentStatusColor(status))
            .frame(width: 9, height: 9)
            .overlay(
                Circle().strokeBorder(Theme.ink.opacity(0.15), lineWidth: 0.5)
            )
    }

    private func agentStatusColor(_ status: String) -> Color {
        switch status {
        case "complete":
            return Color(red: 0.49, green: 0.66, blue: 0.46)
        case "running":
            return Theme.accent
        case "skipped":
            return Theme.inkFaint
        case "failed", "error":
            return Color(red: 0.84, green: 0.40, blue: 0.34)
        default:
            return Theme.inkFaint
        }
    }

    // MARK: Type helpers

    private func heading(_ text: String) -> some View {
        Text(text)
            .font(Theme.serif(24, weight: .semibold))
            .foregroundStyle(Theme.ink)
    }

    private func subheading(_ text: String) -> some View {
        Text(text)
            .font(Theme.serif(16, weight: .semibold))
            .foregroundStyle(Theme.ink)
    }

    private var canSubmit: Bool {
        URL(string: urlText)?.scheme != nil
    }

    // MARK: Networking

    @MainActor
    private func submit() async {
        guard let inputURL = URL(string: urlText) else {
            statusMessage = "Enter a valid URL."
            return
        }

        isSubmitting = true
        statusMessage = "Starting..."
        consumeResponse = nil
        liveAgentTraces = []
        agentLogExpanded = true
        streamedContent = nil
        streamedAnalysis = nil
        streamedHighlights = []
        streamedChapters = []
        learnedKeys = []
        discussion = []
        questionText = ""
        AppDebugLog.write("consume.start", fields: ["url": inputURL.absoluteString])
        defer {
            isSubmitting = false
        }

        do {
            let stream = try await client.consumeStream(url: inputURL)
            for try await event in stream {
                switch event.type {
                case "trace":
                    if let trace = event.trace {
                        updateTrace(trace)
                        statusMessage = trace.summary
                    }
                case "content":
                    if let content = event.content {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            streamedContent = content
                        }
                    }
                case "analysis":
                    if let analysis = event.analysis {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            streamedAnalysis = analysis
                        }
                        statusMessage = "Summary ready"
                    }
                case "highlight":
                    if let highlight = event.highlight {
                        appendStreamedHighlight(highlight)
                        statusMessage = "Highlight \(streamedHighlights.count) ready"
                    }
                case "chapter":
                    if let chapter = event.chapter {
                        appendStreamedChapter(chapter)
                        statusMessage = "Chapter \(streamedChapters.count) ready"
                    }
                case "final":
                    if let response = event.response {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            consumeResponse = response
                            liveAgentTraces = response.agentTraces
                            agentLogExpanded = false
                            streamedContent = nil
                            streamedAnalysis = nil
                            streamedHighlights = []
                            streamedChapters = []
                        }
                        statusMessage = "Ready"
                        urlText = ""
                    }
                case "error":
                    consumeResponse = nil
                    streamedContent = nil
                    streamedAnalysis = nil
                    streamedHighlights = []
                    streamedChapters = []
                    statusMessage = event.message ?? "Backend stream failed."
                    AppDebugLog.write("consume.backend_error", fields: ["message": statusMessage])
                default:
                    break
                }
            }
        } catch {
            consumeResponse = nil
            streamedContent = nil
            streamedAnalysis = nil
            streamedHighlights = []
            streamedChapters = []
            statusMessage = error.localizedDescription
            AppDebugLog.write("consume.client_error", fields: ["message": statusMessage])
        }
    }

    private func updateTrace(_ trace: AgentTrace) {
        if let index = liveAgentTraces.firstIndex(where: { $0.name == trace.name }) {
            liveAgentTraces[index] = trace
        } else {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                liveAgentTraces.append(trace)
            }
        }
    }

    private func appendStreamedHighlight(_ highlight: Highlight) {
        guard !streamedHighlights.contains(where: { $0.id == highlight.id }) else {
            return
        }
        withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) {
            streamedHighlights.append(highlight)
            streamedHighlights.sort { lhs, rhs in
                (lhs.start ?? .greatestFiniteMagnitude) < (rhs.start ?? .greatestFiniteMagnitude)
            }
        }
    }

    private func appendStreamedChapter(_ chapter: Chapter) {
        guard !streamedChapters.contains(where: { $0.id == chapter.id }) else {
            return
        }
        withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) {
            streamedChapters.append(chapter)
            streamedChapters.sort { lhs, rhs in
                (lhs.start ?? .greatestFiniteMagnitude) < (rhs.start ?? .greatestFiniteMagnitude)
            }
        }
    }

    /// Split the model's summary into scannable points, tolerating either
    /// newline-separated bullets or a single prose blob.
    private func summaryPoints(_ summary: String) -> [String] {
        summary
            .split(whereSeparator: \.isNewline)
            .map { line in
                var trimmed = line.trimmingCharacters(in: .whitespaces)
                for marker in ["- ", "• ", "* ", "– ", "— "] where trimmed.hasPrefix(marker) {
                    trimmed = String(trimmed.dropFirst(marker.count))
                    break
                }
                return trimmed
            }
            .filter { !$0.isEmpty }
    }

    private func contentSummary(for response: ContentResponse) -> String {
        if response.kind == "youtube", let language = response.language {
            return "\(response.source) captions, \(language)"
        }
        return response.kind
    }

    // MARK: Result body (summary is the focus)

    private func consumeBody(_ response: ConsumeResponse) -> some View {
        let analysis = response.analysis
        return VStack(alignment: .leading, spacing: 26) {
            headerSection(response.content)

            Divider().overlay(Theme.hairline)

            // Payoff first: TL;DR and key takeaways before the longer-form aids.
            if let tldr = analysis.tldr {
                tldrSection(tldr)
            }
            keyTakeawaysSection(analysis.keyPoints, novel: analysis.novelPoints)
            summarySection(analysis)
            bulletSection(title: "Flow", items: analysis.readingFlow)

            // Context & terms — comprehension scaffolding.
            bulletSection(title: "Context helpers", items: analysis.contextHelpers)
            if !analysis.glossary.isEmpty {
                glossarySection(analysis.glossary)
            }
            visualAidsSection(analysis.visualAids)

            // Navigate the source.
            if !analysis.chapters.isEmpty {
                chaptersSection(
                    analysis.chapters,
                    sourceURL: response.content.url,
                    sourceTitle: response.content.title
                )
            }
            if !analysis.highlights.isEmpty {
                highlightsSection(
                    analysis.highlights,
                    sourceURL: response.content.url,
                    sourceTitle: response.content.title
                )
            }

            researchSection(response)
            discussionSection(response)
            alreadyKnownSection(response)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Header (title, source, thumbnail, original link)

    private func headerSection(_ content: ContentResponse) -> some View {
        HStack(alignment: .top, spacing: 16) {
            if let thumb = thumbnailURL(content) {
                AsyncImage(url: thumb) { image in
                    image.resizable().aspectRatio(contentMode: .fill)
                } placeholder: {
                    Rectangle().fill(Theme.paperRaised)
                }
                .frame(width: 132, height: 84)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline, lineWidth: 1))
            }

            VStack(alignment: .leading, spacing: 6) {
                if let title = content.title {
                    Text(title)
                        .font(Theme.serif(26, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .textSelection(.enabled)
                }
                Text(contentSummary(for: content))
                    .font(Theme.serifItalic(14))
                    .foregroundStyle(Theme.inkFaint)

                if let url = URL(string: content.url) {
                    Link(destination: url) {
                        HStack(spacing: 5) {
                            Image(systemName: "arrow.up.right.square")
                            Text(url.host ?? "Open original")
                        }
                        .font(Theme.text(12, weight: .semibold))
                    }
                    .foregroundStyle(Theme.accent)
                    .padding(.top, 2)
                }
            }

            Spacer(minLength: 0)
        }
    }

    /// Best available preview image for the header — the first content image, if any.
    private func thumbnailURL(_ content: ContentResponse) -> URL? {
        let candidate = content.media.first(where: { $0.kind == "image" }) ?? content.media.first
        guard let urlString = candidate?.url else { return nil }
        return URL(string: urlString)
    }

    // MARK: Distilled sections

    private func tldrSection(_ tldr: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Rectangle()
                .fill(Theme.accent)
                .frame(width: 2)
            Text(tldr)
                .font(Theme.serifItalic(20))
                .foregroundStyle(Theme.ink)
                .textSelection(.enabled)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func summarySection(_ analysis: ConsumptionAnalysis) -> some View {
        let points = analysis.summaryPoints.isEmpty
            ? summaryPoints(analysis.summary)
            : analysis.summaryPoints
        if !points.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                heading("Summary")
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(points, id: \.self) { point in
                        HStack(alignment: .top, spacing: 10) {
                            Text("—")
                                .foregroundStyle(Theme.inkFaint)
                            Text(point)
                                .font(Theme.serif(15))
                                .foregroundStyle(Theme.ink)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func visualAidsSection(_ aids: [VisualAid]) -> some View {
        if !aids.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                subheading("Visual aids")
                ForEach(aids) { aid in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(aid.title)
                            .font(Theme.serif(15, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        Text(aid.explanation)
                            .font(Theme.serif(14))
                            .foregroundStyle(Theme.inkSoft)
                            .textSelection(.enabled)

                        if let urlString = aid.imageURL, let url = URL(string: urlString) {
                            AsyncImage(url: url) { image in
                                image.resizable().aspectRatio(contentMode: .fit)
                            } placeholder: {
                                ProgressView().controlSize(.small)
                            }
                            .frame(maxWidth: 440, maxHeight: 300)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline, lineWidth: 1))
                        } else if let diagram = aid.suggestedDiagram {
                            Text(diagram)
                                .font(Theme.serifItalic(13))
                                .foregroundStyle(Theme.inkFaint)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Theme.paper)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                                .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.hairline, lineWidth: 1))
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func researchSection(_ response: ConsumeResponse) -> some View {
        let analysis = response.analysis
        let hasResearch = !analysis.researchContext.isEmpty
            || !analysis.researchHighlights.isEmpty
            || !response.researchDocuments.isEmpty
        if hasResearch {
            VStack(alignment: .leading, spacing: 14) {
                heading("Research")
                bulletSection(title: "Context", items: analysis.researchContext)
                if !analysis.researchHighlights.isEmpty {
                    researchHighlightsSection(analysis.researchHighlights)
                }
                if !response.researchDocuments.isEmpty {
                    researchLinksSection(response.researchDocuments)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func alreadyKnownSection(_ response: ConsumeResponse) -> some View {
        let known = response.analysis.alreadyKnown
        let matches = response.knowledgeMatches
        if !known.isEmpty || !matches.isEmpty {
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 12) {
                    bulletSection(title: "Skipped — already known", items: known)
                    ForEach(matches) { match in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(match.title ?? match.url)
                                .font(Theme.serif(14, weight: .semibold))
                                .foregroundStyle(Theme.inkSoft)
                            Text(match.summary)
                                .font(Theme.serif(13))
                                .foregroundStyle(Theme.inkFaint)
                                .lineLimit(3)
                                .textSelection(.enabled)
                        }
                    }
                }
                .padding(.top, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Text("Already known")
                    .font(Theme.serif(14, weight: .semibold))
                    .foregroundStyle(Theme.inkSoft)
            }
            .tint(Theme.inkSoft)
        }
    }

    private func hasAnalysis(_ analysis: ConsumptionAnalysis) -> Bool {
        !analysis.summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !analysis.summaryPoints.isEmpty
    }

    private func liveDigestPanel() -> some View {
        VStack(alignment: .leading, spacing: 20) {
            if let content = streamedContent {
                headerSection(content)
            }

            if let analysis = streamedAnalysis, hasAnalysis(analysis) {
                if let tldr = analysis.tldr {
                    tldrSection(tldr)
                }
                keyTakeawaysSection(analysis.keyPoints, novel: analysis.novelPoints)
                summarySection(analysis)
                bulletSection(title: "Flow", items: analysis.readingFlow)
                bulletSection(title: "Context helpers", items: analysis.contextHelpers)
                if !analysis.glossary.isEmpty {
                    glossarySection(analysis.glossary)
                }
                visualAidsSection(analysis.visualAids)
            }

            if !streamedChapters.isEmpty {
                chaptersSection(
                    streamedChapters,
                    sourceURL: streamedContent?.url ?? "",
                    sourceTitle: streamedContent?.title
                )
            }

            if !streamedHighlights.isEmpty {
                highlightsSection(
                    streamedHighlights,
                    sourceURL: streamedContent?.url ?? "",
                    sourceTitle: streamedContent?.title
                )
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Discussion

    private func discussionSection(_ response: ConsumeResponse) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Divider().overlay(Theme.hairline)
            heading("Discuss")

            if discussion.isEmpty && !response.analysis.deepDiveQuestions.isEmpty {
                deepDivePrompts(response)
            }

            ForEach(discussion) { turn in
                discussionTurnView(turn)
            }

            HStack(spacing: 10) {
                TextField("Ask gemma about this…", text: $questionText)
                    .textFieldStyle(VintageFieldStyle())
                    .onSubmit { Task { await ask(response) } }
                    .disabled(isDiscussing)

                Button {
                    Task { await ask(response) }
                } label: {
                    if isDiscussing {
                        ProgressView().controlSize(.small).tint(Theme.paper)
                    } else {
                        Text("Ask")
                    }
                }
                .buttonStyle(VintageButtonStyle())
                .disabled(isDiscussing || questionText.trimmingCharacters(in: .whitespaces).isEmpty)
                .opacity((isDiscussing || questionText.trimmingCharacters(in: .whitespaces).isEmpty) ? 0.45 : 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Clickable starter questions from the model's deep-dive suggestions;
    /// tapping one asks it immediately.
    private func deepDivePrompts(_ response: ConsumeResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Start with…")
                .font(Theme.text(11, weight: .semibold))
                .tracking(1.5)
                .foregroundStyle(Theme.inkFaint)

            ForEach(response.analysis.deepDiveQuestions, id: \.self) { question in
                Button {
                    questionText = question
                    Task { await ask(response) }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.turn.down.right")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(Theme.accent)
                        Text(question)
                            .font(Theme.serif(14))
                            .foregroundStyle(Theme.ink)
                            .multilineTextAlignment(.leading)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .overlay(RoundedRectangle(cornerRadius: 7).strokeBorder(Theme.hairline, lineWidth: 1))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(isDiscussing)
            }
        }
    }

    private func discussionTurnView(_ turn: DiscussTurn) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("YOU")
                    .font(Theme.text(10, weight: .semibold))
                    .tracking(1.5)
                    .foregroundStyle(Theme.accent)
                Text(turn.question)
                    .font(Theme.serif(15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .textSelection(.enabled)
            }

            if !turn.thinking.isEmpty {
                thinkingBlock(turn.thinking, streaming: turn.isStreaming && turn.answer.isEmpty)
            }

            if !turn.answer.isEmpty {
                Text(turn.answer)
                    .font(Theme.serif(16))
                    .foregroundStyle(Theme.ink)
                    .textSelection(.enabled)
            } else if turn.isStreaming && turn.thinking.isEmpty {
                Text("Thinking…")
                    .font(Theme.serifItalic(14))
                    .foregroundStyle(Theme.inkFaint)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
    }

    private func thinkingBlock(_ text: String, streaming: Bool) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text("THINKING")
                    .font(Theme.text(10, weight: .semibold))
                    .tracking(2)
                    .foregroundStyle(Theme.inkFaint)
                if streaming {
                    ProgressView().controlSize(.mini).tint(Theme.inkFaint)
                }
            }
            Text(text)
                .font(Theme.serif(13))
                .foregroundStyle(Theme.inkFaint)
                .textSelection(.enabled)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.paper)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline, lineWidth: 1)
        )
    }

    @MainActor
    private func ask(_ response: ConsumeResponse) async {
        let question = questionText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !question.isEmpty, !isDiscussing else { return }

        questionText = ""
        isDiscussing = true

        var history: [[String: String]] = []
        for turn in discussion {
            history.append(["role": "user", "content": turn.question])
            if !turn.answer.isEmpty {
                history.append(["role": "assistant", "content": turn.answer])
            }
        }

        discussion.append(DiscussTurn(question: question))
        let index = discussion.count - 1

        do {
            let stream = try await client.discussStream(
                question: question,
                context: response.content.text,
                title: response.content.title,
                history: history
            )
            for try await event in stream {
                switch event.type {
                case "thinking":
                    discussion[index].thinking += event.text ?? ""
                case "answer":
                    discussion[index].answer += event.text ?? ""
                case "done":
                    discussion[index].isStreaming = false
                case "error":
                    discussion[index].answer += "\n[Error: \(event.message ?? "discussion failed")]"
                    discussion[index].isStreaming = false
                default:
                    break
                }
            }
        } catch {
            discussion[index].answer += "\n[Error: \(error.localizedDescription)]"
        }

        discussion[index].isStreaming = false
        isDiscussing = false
    }

    @ViewBuilder
    private func keyTakeawaysSection(_ items: [String], novel: [String] = []) -> some View {
        if !items.isEmpty || !novel.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                heading("Key takeaways")

                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                        HStack(alignment: .top, spacing: 10) {
                            Text("\(index + 1)")
                                .font(Theme.mono(12).weight(.semibold))
                                .foregroundStyle(Theme.paper)
                                .frame(width: 24, height: 24)
                                .background(Theme.accent)
                                .clipShape(Circle())

                            Text(item)
                                .font(Theme.serif(15))
                                .foregroundStyle(Theme.ink)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }

                if !novel.isEmpty {
                    newToYouBlock(novel)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// The "it remembers what you know" payoff: points that are new to you,
    /// versus what you've already consumed before.
    private func newToYouBlock(_ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11, weight: .semibold))
                Text("NEW TO YOU")
                    .font(Theme.text(10, weight: .semibold))
                    .tracking(2)
            }
            .foregroundStyle(Theme.accent)

            ForEach(items, id: \.self) { item in
                HStack(alignment: .top, spacing: 10) {
                    Text("—").foregroundStyle(Theme.accent)
                    Text(item)
                        .font(Theme.serif(15))
                        .foregroundStyle(Theme.ink)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.accent.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.accent.opacity(0.3), lineWidth: 1))
    }

    private func researchHighlightsSection(_ highlights: [ResearchHighlight]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            subheading("Research highlights")

            ForEach(highlights) { highlight in
                VStack(alignment: .leading, spacing: 5) {
                    if let url = URL(string: highlight.url) {
                        Link(highlight.title, destination: url)
                            .font(Theme.serif(15, weight: .semibold))
                    } else {
                        Text(highlight.title)
                            .font(Theme.serif(15, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                    }

                    Text(highlight.point)
                        .font(Theme.serif(14))
                        .foregroundStyle(Theme.ink)
                        .textSelection(.enabled)
                    Text(highlight.whyItMatters)
                        .font(Theme.serifItalic(13))
                        .foregroundStyle(Theme.inkSoft)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func glossarySection(_ terms: [TermExplanation]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            subheading("Terms")

            ForEach(terms) { item in
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.term)
                        .font(Theme.serif(15, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    Text(item.explanation)
                        .font(Theme.serif(14))
                        .foregroundStyle(Theme.inkSoft)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func highlightsSection(_ highlights: [Highlight], sourceURL: String, sourceTitle: String?) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            heading("Highlights")

            ForEach(orderedHighlights(highlights)) { highlight in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .top, spacing: 10) {
                        if let range = highlight.timeRange {
                            Text(range)
                                .font(Theme.mono(12).weight(.semibold))
                                .foregroundStyle(Theme.accent)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Theme.accent.opacity(0.12))
                                .clipShape(RoundedRectangle(cornerRadius: 5))
                                .fixedSize()
                        }

                        VStack(alignment: .leading, spacing: 5) {
                            Text(highlight.text)
                                .font(Theme.serif(15, weight: .semibold))
                                .foregroundStyle(Theme.ink)
                                .textSelection(.enabled)

                            if let summary = highlight.cleanSummary, summary != highlight.text {
                                Text(summary)
                                    .font(Theme.serif(14))
                                    .foregroundStyle(Theme.ink)
                                    .textSelection(.enabled)
                            }
                        }

                        Spacer(minLength: 8)

                        learnedButton(
                            key: "\(sourceURL)|highlight|\(highlight.id)",
                            kind: "highlight",
                            sourceURL: sourceURL,
                            sourceTitle: sourceTitle,
                            title: highlight.text,
                            summary: highlight.cleanSummary ?? highlight.why,
                            detail: highlight.caption
                        )
                    }

                    Text(highlight.why)
                        .font(Theme.serifItalic(14))
                        .foregroundStyle(Theme.inkSoft)
                        .textSelection(.enabled)

                    if let caption = highlight.caption,
                       !caption.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        captionBlock(caption)
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func chaptersSection(_ chapters: [Chapter], sourceURL: String, sourceTitle: String?) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            heading("Chapters")

            ForEach(orderedChapters(chapters)) { chapter in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        if let range = chapter.timeRange {
                            Text(range)
                                .font(Theme.mono(12).weight(.semibold))
                                .foregroundStyle(Theme.accent)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Theme.accent.opacity(0.12))
                                .clipShape(RoundedRectangle(cornerRadius: 5))
                                .fixedSize()
                        }

                        Text(chapter.title)
                            .font(Theme.serif(15, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .textSelection(.enabled)

                        Spacer(minLength: 8)

                        learnedButton(
                            key: "\(sourceURL)|chapter|\(chapter.id)",
                            kind: "chapter",
                            sourceURL: sourceURL,
                            sourceTitle: sourceTitle,
                            title: chapter.title,
                            summary: chapter.summary,
                            detail: chapter.caption
                        )
                    }

                    Text(chapter.summary)
                        .font(Theme.serif(14))
                        .foregroundStyle(Theme.inkSoft)
                        .textSelection(.enabled)

                    if let caption = chapter.caption,
                       !caption.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        captionBlock(caption)
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func captionBlock(_ caption: String) -> some View {
        DisclosureGroup {
            Text(caption)
                .font(Theme.serif(13))
                .foregroundStyle(Theme.inkSoft)
                .textSelection(.enabled)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 4)
        } label: {
            Text("Transcript")
                .font(Theme.serif(13, weight: .semibold))
                .foregroundStyle(Theme.accent)
        }
        .tint(Theme.accent)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6)
    }

    private func learnedButton(
        key: String,
        kind: String,
        sourceURL: String,
        sourceTitle: String?,
        title: String,
        summary: String,
        detail: String?
    ) -> some View {
        let isLearned = learnedKeys.contains(key)
        return Button {
            guard !isLearned else { return }
            learnedKeys.insert(key)
            Task {
                await learn(
                    key: key,
                    kind: kind,
                    sourceURL: sourceURL,
                    sourceTitle: sourceTitle,
                    title: title,
                    summary: summary,
                    detail: detail
                )
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: isLearned ? "checkmark.seal.fill" : "graduationcap")
                    .font(.system(size: 10, weight: .semibold))
                Text(isLearned ? "Learned" : "Mark as learned")
                    .font(Theme.text(11, weight: .semibold))
            }
            .foregroundStyle(isLearned ? Theme.accent : Theme.inkSoft)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .overlay(
                Capsule().strokeBorder(
                    isLearned ? Theme.accent.opacity(0.55) : Theme.hairline,
                    lineWidth: 1
                )
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(isLearned)
        .help("Save this as personal knowledge so Defluff compresses it next time")
    }

    @MainActor
    private func learn(
        key: String,
        kind: String,
        sourceURL: String,
        sourceTitle: String?,
        title: String,
        summary: String,
        detail: String?
    ) async {
        do {
            try await client.learn(
                kind: kind,
                sourceURL: sourceURL,
                sourceTitle: sourceTitle,
                title: title,
                summary: summary,
                detail: detail
            )
            AppDebugLog.write("learn.ok", fields: ["kind": kind, "title": title])
        } catch {
            learnedKeys.remove(key)
            AppDebugLog.write("learn.error", fields: ["message": error.localizedDescription])
        }
    }

    private func orderedHighlights(_ highlights: [Highlight]) -> [Highlight] {
        highlights.sorted {
            ($0.start ?? .greatestFiniteMagnitude) < ($1.start ?? .greatestFiniteMagnitude)
        }
    }

    private func orderedChapters(_ chapters: [Chapter]) -> [Chapter] {
        chapters.sorted {
            ($0.start ?? .greatestFiniteMagnitude) < ($1.start ?? .greatestFiniteMagnitude)
        }
    }

    private func researchLinksSection(_ documents: [ResearchDocument]) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            subheading("Links")

            ForEach(documents) { document in
                VStack(alignment: .leading, spacing: 5) {
                    if let url = URL(string: document.url) {
                        Link(document.title ?? document.url, destination: url)
                            .font(Theme.serif(16, weight: .semibold))
                    } else {
                        Text(document.title ?? document.url)
                            .font(Theme.serif(16, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                    }

                    if let host = URL(string: document.url)?.host {
                        Text(host)
                            .font(Theme.serif(12, weight: .semibold))
                            .foregroundStyle(Theme.accent)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func bulletSection(title: String, items: [String]) -> some View {
        Group {
            if !items.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    subheading(title)
                    ForEach(items, id: \.self) { item in
                        HStack(alignment: .top, spacing: 10) {
                            Text("—")
                                .foregroundStyle(Theme.inkFaint)
                            Text(item)
                                .font(Theme.serif(15))
                                .foregroundStyle(Theme.ink)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
        }
    }

}

private struct WindowFullScreenSizer: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            guard let window = view.window else {
                return
            }

            let screen = window.screen ?? NSScreen.main
            guard let visibleFrame = screen?.visibleFrame else {
                return
            }

            window.setFrame(visibleFrame, display: true)
            window.minSize = NSSize(width: 900, height: 600)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}

struct DiscussTurn: Identifiable {
    let id = UUID()
    let question: String
    var thinking: String = ""
    var answer: String = ""
    var isStreaming: Bool = true
}

#Preview {
    ContentView(client: BackendClient())
}
