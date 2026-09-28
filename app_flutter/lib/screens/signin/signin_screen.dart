import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../theme/evergreen_theme.dart';

enum _Mode { signIn, signUp }

/// Sign in, sign up, and "Try demo" (IRA-38) — mirrors `ui/index.html`'s `#authGate` card.
class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  _Mode _mode = _Mode.signIn;
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nameController = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final notifier = ref.read(authProvider.notifier);
      if (_mode == _Mode.signIn) {
        await notifier.login(_emailController.text.trim(), _passwordController.text);
      } else {
        await notifier.signup(_emailController.text.trim(), _passwordController.text, _nameController.text.trim());
      }
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _tryDemo() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(authProvider.notifier).startDemo();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Card(
            margin: const EdgeInsets.all(24),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    _mode == _Mode.signIn ? 'Sign in' : 'Create account',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 20),
                  if (_mode == _Mode.signUp) ...[
                    TextField(
                      controller: _nameController,
                      decoration: const InputDecoration(labelText: 'Name'),
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextField(
                    controller: _emailController,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _passwordController,
                    decoration: const InputDecoration(labelText: 'Password'),
                    obscureText: true,
                    onSubmitted: (_) => _submit(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: EvergreenColors.refused)),
                  ],
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed: _submitting ? null : _submit,
                    child: Text(_mode == _Mode.signIn ? 'Sign in' : 'Sign up'),
                  ),
                  const SizedBox(height: 10),
                  OutlinedButton(
                    onPressed: _submitting ? null : _tryDemo,
                    child: const Text('Try demo'),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => setState(() => _mode = _mode == _Mode.signIn ? _Mode.signUp : _Mode.signIn),
                    child: Text(_mode == _Mode.signIn ? "Don't have an account? Sign up" : 'Already have an account? Sign in'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
