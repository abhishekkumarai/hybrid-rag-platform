/// Mirrors contracts/identity.py.
class User {
  final String id;
  final String email;
  final String displayName;
  final bool isAdmin;
  final bool isDemo;
  final double createdAt;

  const User({
    required this.id,
    required this.email,
    this.displayName = '',
    this.isAdmin = false,
    this.isDemo = false,
    this.createdAt = 0,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as String,
        email: json['email'] as String,
        displayName: json['display_name'] as String? ?? '',
        isAdmin: json['is_admin'] as bool? ?? false,
        isDemo: json['is_demo'] as bool? ?? false,
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'display_name': displayName,
        'is_admin': isAdmin,
        'is_demo': isDemo,
        'created_at': createdAt,
      };
}

typedef WorkspaceRole = String; // "owner" | "admin" | "member"

class Workspace {
  final String id;
  final String name;
  final String ownerId;
  final double createdAt;

  const Workspace({
    required this.id,
    required this.name,
    required this.ownerId,
    this.createdAt = 0,
  });

  factory Workspace.fromJson(Map<String, dynamic> json) => Workspace(
        id: json['id'] as String,
        name: json['name'] as String,
        ownerId: json['owner_id'] as String,
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
      );
}

class WorkspaceMember {
  final String workspaceId;
  final String userId;
  final WorkspaceRole role;
  final double addedAt;

  const WorkspaceMember({
    required this.workspaceId,
    required this.userId,
    this.role = 'member',
    this.addedAt = 0,
  });

  factory WorkspaceMember.fromJson(Map<String, dynamic> json) => WorkspaceMember(
        workspaceId: json['workspace_id'] as String,
        userId: json['user_id'] as String,
        role: json['role'] as String? ?? 'member',
        addedAt: (json['added_at'] as num?)?.toDouble() ?? 0,
      );
}

class WorkspaceMemberEntry {
  final WorkspaceMember member;
  final User user;

  const WorkspaceMemberEntry({required this.member, required this.user});

  factory WorkspaceMemberEntry.fromJson(Map<String, dynamic> json) => WorkspaceMemberEntry(
        member: WorkspaceMember.fromJson(json['member'] as Map<String, dynamic>),
        user: User.fromJson(json['user'] as Map<String, dynamic>),
      );
}
