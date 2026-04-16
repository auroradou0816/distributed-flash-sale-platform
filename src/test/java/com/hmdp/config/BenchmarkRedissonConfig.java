package com.hmdp.config;

import cn.hutool.core.util.StrUtil;
import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.redisson.config.SingleServerConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("benchmark")
public class BenchmarkRedissonConfig {

    @Primary
    @Bean("benchmarkRedissonClient")
    public RedissonClient benchmarkRedissonClient(@Value("${spring.redis.host}") String host,
                                                  @Value("${spring.redis.port}") Integer port,
                                                  @Value("${spring.redis.password:}") String password) {
        Config config = new Config();
        SingleServerConfig singleServerConfig = config.useSingleServer()
                .setAddress("redis://" + host + ":" + port);
        if (StrUtil.isNotBlank(password)) {
            singleServerConfig.setPassword(password);
        }
        return Redisson.create(config);
    }
}
