resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "${var.name_prefix}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      if (uri.indexOf('.') === -1 || uri.endsWith('/')) {
        request.uri = '/index.html';
      }

      return request;
    }
  JS
}
