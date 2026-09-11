import Foundation

/// A typed query builder over Supabase's PostgREST, mirroring the calls the web
/// client already makes — `.from("posts").select(...).eq(...).order(...)`.
///
/// The same row-level security applies here as in the browser: the access token
/// is sent on every request, and the database decides what this user may see.
/// Nothing is trusted to the client, which is why the app can talk to the
/// database directly at all.
struct Query: Sendable {
    let table: String
    private var columns: String = "*"
    private var filters: [URLQueryItem] = []
    private var ordering: URLQueryItem?
    private var limitValue: Int?
    private var rangeValue: (from: Int, to: Int)?

    init(_ table: String) { self.table = table }

    func select(_ columns: String) -> Query {
        var copy = self; copy.columns = columns; return copy
    }

    func eq(_ column: String, _ value: String) -> Query {
        var copy = self; copy.filters.append(.init(name: column, value: "eq.\(value)")); return copy
    }

    func neq(_ column: String, _ value: String) -> Query {
        var copy = self; copy.filters.append(.init(name: column, value: "neq.\(value)")); return copy
    }

    func `in`(_ column: String, _ values: [String]) -> Query {
        var copy = self
        copy.filters.append(.init(name: column, value: "in.(\(values.joined(separator: ",")))"))
        return copy
    }

    func gt(_ column: String, _ value: String) -> Query {
        var copy = self; copy.filters.append(.init(name: column, value: "gt.\(value)")); return copy
    }

    func isNull(_ column: String) -> Query {
        var copy = self; copy.filters.append(.init(name: column, value: "is.null")); return copy
    }

    /// Case-insensitive contains — what a username search wants.
    func ilike(_ column: String, contains term: String) -> Query {
        var copy = self
        copy.filters.append(.init(name: column, value: "ilike.*\(term)*"))
        return copy
    }

    func order(_ column: String, ascending: Bool = false) -> Query {
        var copy = self
        copy.ordering = .init(name: "order", value: "\(column).\(ascending ? "asc" : "desc")")
        return copy
    }

    func limit(_ count: Int) -> Query {
        var copy = self; copy.limitValue = count; return copy
    }

    /// Paging by row range, which is how an infinite feed should ask for its
    /// next page: `range(from: 20, to: 39)` is rows 21–40.
    func range(from: Int, to: Int) -> Query {
        var copy = self; copy.rangeValue = (from, to); return copy
    }

    func queryItems() -> [URLQueryItem] {
        var items = [URLQueryItem(name: "select", value: columns)]
        items.append(contentsOf: filters)
        if let ordering { items.append(ordering) }
        if let limitValue { items.append(.init(name: "limit", value: String(limitValue))) }
        return items
    }

    var rangeHeader: String? {
        rangeValue.map { "\($0.from)-\($0.to)" }
    }
}

/// Runs queries. One instance for the app; it borrows the live access token
/// from AuthStore on every call rather than caching one that may have expired.
@MainActor
@Observable
final class Database {
    private let config: AppConfig
    private let auth: AuthStore
    private let http = HTTP()

    init(config: AppConfig, auth: AuthStore) {
        self.config = config
        self.auth = auth
    }

    func fetch<T: Decodable>(_ query: Query, as type: T.Type = T.self) async throws -> [T] where T: Sendable {
        let request = try await request(for: query, method: "GET")
        return try await http.send(request, as: [T].self)
    }

    func first<T: Decodable>(_ query: Query, as type: T.Type = T.self) async throws -> T? where T: Sendable {
        try await fetch(query.limit(1), as: T.self).first
    }

    @discardableResult
    func insert(into table: String, _ row: some Encodable & Sendable) async throws -> Data {
        var request = try await request(for: Query(table), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("return=representation", forHTTPHeaderField: "Prefer")
        request.httpBody = try HTTP.encoder.encode(row)
        return try await http.send(request)
    }

    @discardableResult
    func update(_ query: Query, _ changes: some Encodable & Sendable) async throws -> Data {
        var request = try await request(for: query, method: "PATCH")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("return=representation", forHTTPHeaderField: "Prefer")
        request.httpBody = try HTTP.encoder.encode(changes)
        return try await http.send(request)
    }

    func delete(_ query: Query) async throws {
        _ = try await http.send(try await request(for: query, method: "DELETE"))
    }

    private func request(for query: Query, method: String) async throws -> URLRequest {
        guard let supabaseURL = config.supabaseURL else {
            throw HTTPError(status: -1, message: "The app has not finished starting up.", body: nil)
        }
        var components = URLComponents(
            url: supabaseURL.appending(path: "rest/v1/\(query.table)"),
            resolvingAgainstBaseURL: false
        )!
        if method == "GET" { components.queryItems = query.queryItems() }
        else { components.queryItems = query.queryItems().filter { $0.name != "select" } }

        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue(config.anonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(try await auth.validAccessToken())", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let range = query.rangeHeader {
            request.setValue(range, forHTTPHeaderField: "Range")
        }
        return request
    }
}
